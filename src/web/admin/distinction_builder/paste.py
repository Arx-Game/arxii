"""Add from a table: additions-only bulk entry of distinctions on the Builder (#3709).

Staff paste one row per distinction (pipe-separated, ``COLUMNS`` order); the view
parses every row, resolves every name it carries against rows that already exist
(a category, a modifier target, an enemy reason, an Appearance section, a Beginning,
a Glimpse tag, an Upbringing answer, a schooling line), and shows a preview: each
row reads ``create``, ``skip`` (its slug already exists, or an identical offer line
does) or ``error``. Nothing is written until every row reads create or skip; then a
digest-guarded confirm creates the rows in one transaction, crediting the operator.

The rules that make it safe to keep (ruled 2026-09-08): it never updates a row that
exists, never deletes, never creates a referenced row, previews before it writes,
writes all or nothing, and is superuser-only. There is no bulk-edit mode; that would
need its own ruling. The digest idiom mirrors ``content_row_export_views``: the
confirm POST re-parses the same text against the same database and refuses if the
preview it is confirming no longer matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re

from django.contrib import messages
from django.contrib.admin.models import ADDITION, LogEntry
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_written
from web.admin.tuning.views import superuser_required
from world.character_creation.constants import (
    ENEMY_MARKING_DEGREES,
    ActorSheetPrompt,
    OfferArrival,
    OfferChapter,
)
from world.character_creation.models import (
    AppearanceSection,
    Beginnings,
    DistinctionOffer,
    EnemyReason,
    OriginTemplateSlotChoice,
    SchoolingLine,
)
from world.contributors.models import ContentContributor
from world.distinctions.models import Distinction, DistinctionCategory, DistinctionEffect
from world.magic.models import GlimpseTag
from world.mechanics.models import ModifierTarget

COLUMNS: tuple[str, ...] = (
    "name",
    "category",
    "cost_per_rank",
    "max_rank",
    "player_line",
    "description",
    "effects",
    "offered_under",
    "first_look_for",
)
STATUS_CREATE = "create"
STATUS_SKIP = "skip"
STATUS_ERROR = "error"
ACTION_CHECK = "check"
ACTION_CREATE = "create"

_PROMPT_WORDS = {
    "rules": ActorSheetPrompt.NEVER_DO,
    "devotions": ActorSheetPrompt.PROTECT,
    "fears": ActorSheetPrompt.FEAR,
    **{p.value: p for p in ActorSheetPrompt},
}
_KIND_DEGREE = "degree"
_EFFECT_RE = re.compile(r"^([+-])\s*(\d+)?\s*(.+)$")


@dataclass
class EffectSpec:
    target_id: int
    value: int | None
    immune: bool
    label: str


@dataclass
class OfferSpec:
    chapter: str
    arrives_as: str
    opener_field: str
    opener_value: int | str
    label: str


@dataclass
class RowSpec:
    line_no: int
    name: str
    slug: str = ""
    category_id: int | None = None
    cost_per_rank: int = 0
    max_rank: int = 1
    player_line: str = ""
    description: str = ""
    effects: list[EffectSpec] = field(default_factory=list)
    offers: list[OfferSpec] = field(default_factory=list)
    first_look_ids: list[int] = field(default_factory=list)
    first_look_names: list[str] = field(default_factory=list)
    status: str = STATUS_CREATE
    notes: list[str] = field(default_factory=list)

    def fail(self, note: str) -> None:
        self.status = STATUS_ERROR
        self.notes.append(note)

    @property
    def will_create(self) -> str:
        kind = "award" if self.cost_per_rank < 0 else "cost"
        parts = [f"Distinction ({kind} {abs(self.cost_per_rank)})"]
        if self.effects:
            effects = "; ".join(e.label for e in self.effects)
            parts.append(f"{len(self.effects)} effect(s): {effects}")
        if self.offers:
            offers = "; ".join(o.label for o in self.offers)
            parts.append(f"{len(self.offers)} offer line(s): {offers}")
        if self.first_look_names:
            parts.append(f"pinned for {', '.join(self.first_look_names)}")
        return "; ".join(parts)


def _one(qs: QuerySet, what: str) -> tuple[object | None, str]:
    """Exactly one row, or the reason there is not."""
    rows = list(qs[:2])
    if not rows:
        return None, f"unknown {what}"
    if len(rows) > 1:
        return None, f"ambiguous {what}"
    return rows[0], ""


def _int(raw: str, default: int, what: str, row: RowSpec) -> int:
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        row.fail(f"{what} is not a whole number: {raw!r}")
        return default


def _parse_effects(raw: str, row: RowSpec) -> None:
    for token in (t.strip() for t in raw.split(";") if t.strip()):
        immune = token.lower().startswith("immune:")
        if immune:
            target_raw, sign, magnitude = token[len("immune:") :].strip(), "", None
        else:
            m = _EFFECT_RE.match(token)
            if m is None:
                row.fail(f"effect {token!r} must read +Target, -Target or immune:Target")
                continue
            sign, magnitude, target_raw = m.group(1), m.group(2), m.group(3).strip()
        target, why = _one(
            ModifierTarget.objects.filter(name__iexact=target_raw.replace(" ", "_")),
            f"modifier target {target_raw!r}",
        )
        if target is None:
            target, why = _one(
                ModifierTarget.objects.filter(name__iexact=target_raw),
                f"modifier target {target_raw!r}",
            )
        if target is None:
            row.fail(why)
            continue
        value = None if immune else int(magnitude or 1) * (-1 if sign == "-" else 1)
        row.effects.append(EffectSpec(target.pk, value, immune, token))


#: ``offered_under`` kinds that resolve a row by name: kind -> (chapter, field, model, what).
_NAMED_OPENERS: dict[str, tuple[str, str, type, str]] = {
    "reason": (OfferChapter.ENEMY, "enemy_reason_id", EnemyReason, "reason"),
    "appearance": (OfferChapter.APPEARANCE, "appearance_section_id", AppearanceSection, "section"),
    "glimpse": (OfferChapter.GLIMPSE, "glimpse_tag_id", GlimpseTag, "Glimpse tag"),
    "lineage": (OfferChapter.LINEAGE, "origin_choice_id", OriginTemplateSlotChoice, "answer"),
    "schooling": (
        OfferChapter.TRADITION_STEP,
        "schooling_line_id",
        SchoolingLine,
        "schooling line",
    ),
}


def _opener_spec(kind: str, value: str, token: str) -> tuple[OfferSpec | None, str]:
    """One ``offered_under`` token -> the offer line it names, or why it cannot."""
    if kind in _PROMPT_WORDS:
        prompt = _PROMPT_WORDS[kind]
        spec = OfferSpec(OfferChapter.ACTORS_SHEET, OfferArrival.CHOICE, "prompt", prompt, token)
        return spec, ""
    if kind == _KIND_DEGREE:
        if value not in ENEMY_MARKING_DEGREES:
            return None, f"degree {value!r} does not mark the character (ruined or destroy)"
        spec = OfferSpec(OfferChapter.ENEMY, OfferArrival.BUNDLED, "enemy_degree", value, token)
        return spec, ""
    named = _NAMED_OPENERS.get(kind)
    if named is None:
        return None, f"offered_under {token!r} is not a known opener"
    chapter, opener_field, model, what = named
    row, why = _one(model.objects.filter(name__iexact=value), f"{what} {value!r}")
    if row is None:
        return None, why
    return OfferSpec(chapter, OfferArrival.CHOICE, opener_field, row.pk, token), ""


def _parse_offers(raw: str, row: RowSpec) -> None:
    for token in (t.strip() for t in raw.split(";") if t.strip()):
        kind, _, value = token.partition(":")
        spec, why = _opener_spec(kind.strip().lower(), value.strip(), token)
        if spec is None:
            row.fail(why)
        else:
            row.offers.append(spec)


def _parse_first_look(raw: str, row: RowSpec) -> None:
    for name in (n.strip() for n in raw.split(",") if n.strip()):
        beginning, why = _one(
            Beginnings.objects.filter(name__iexact=name, is_active=True), f"Beginning {name!r}"
        )
        if beginning is None:
            row.fail(why)
        else:
            row.first_look_ids.append(beginning.pk)
            row.first_look_names.append(beginning.name)


def _parse_row(line_no: int, cells: list[str]) -> RowSpec:
    cells = [c.strip() for c in cells] + [""] * (len(COLUMNS) - len(cells))
    values = dict(zip(COLUMNS, cells, strict=False))
    row = RowSpec(line_no=line_no, name=values["name"])
    if not row.name:
        row.fail("no name")
        return row
    row.slug = slugify(row.name)
    category, why = _one(
        DistinctionCategory.objects.filter(name__iexact=values["category"]),
        f"category {values['category']!r}",
    )
    if category is None:
        row.fail(why)
    else:
        row.category_id = category.pk
    row.cost_per_rank = _int(values["cost_per_rank"], 0, "cost per rank", row)
    row.max_rank = max(1, _int(values["max_rank"], 1, "max rank", row))
    row.player_line = values["player_line"][:200]
    row.description = values["description"]
    _parse_effects(values["effects"], row)
    _parse_offers(values["offered_under"], row)
    _parse_first_look(values["first_look_for"], row)
    if row.status == STATUS_ERROR:
        return row
    if Distinction.objects.filter(slug=row.slug).exists():
        row.status = STATUS_SKIP
        row.notes.append(
            f"slug {row.slug!r} already exists; edit the existing row on its Builder page"
        )
    return row


def parse_table(text: str) -> list[RowSpec]:
    """Every non-blank line of ``text`` as a ``RowSpec``, resolved against the database."""
    rows: list[RowSpec] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.count("|") == 0:
            row = RowSpec(line_no=line_no, name=line.strip()[:100])
            row.fail("no pipe-separated columns")
            rows.append(row)
            continue
        rows.append(_parse_row(line_no, line.split("|")))
    seen: set[str] = set()
    for row in rows:
        if row.slug and row.slug in seen and row.status == STATUS_CREATE:
            row.fail(f"slug {row.slug!r} appears twice in this table")
        seen.add(row.slug)
    return rows


def table_digest(rows: list[RowSpec]) -> str:
    """A digest of exactly what the preview showed: rows, statuses, resolved ids."""
    payload = [
        {
            "name": r.name,
            "slug": r.slug,
            "status": r.status,
            "category": r.category_id,
            "cost": r.cost_per_rank,
            "max_rank": r.max_rank,
            "effects": [(e.target_id, e.value, e.immune) for e in r.effects],
            "offers": [(o.chapter, o.arrives_as, o.opener_field, o.opener_value) for o in r.offers],
            "pins": r.first_look_ids,
        }
        for r in rows
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _create_rows(rows: list[RowSpec], contributor: ContentContributor, user_id: int) -> int:
    """Create every ``create`` row's distinction, effects, offer lines and pins; one transaction."""
    created = 0
    with transaction.atomic():
        for row in rows:
            if row.status != STATUS_CREATE:
                continue
            distinction = Distinction.objects.create(
                name=row.name,
                slug=row.slug,
                category_id=row.category_id,
                cost_per_rank=row.cost_per_rank,
                max_rank=row.max_rank,
                description=row.description,
            )
            stamp_written(distinction, contributor)
            for fx in row.effects:
                effect = DistinctionEffect.objects.create(
                    distinction=distinction,
                    target_id=fx.target_id,
                    value_per_rank=fx.value,
                    grants_immunity_to_negative=fx.immune,
                    description=fx.label,
                )
                stamp_written(effect, contributor)
            for spec in row.offers:
                offer = DistinctionOffer.objects.create(
                    distinction=distinction,
                    chapter=spec.chapter,
                    arrives_as=spec.arrives_as,
                    player_line=row.player_line,
                    **{spec.opener_field: spec.opener_value},
                )
                stamp_written(offer, contributor)
                if row.first_look_ids:
                    offer.first_look.set(row.first_look_ids)
            LogEntry.objects.log_actions(
                user_id, [distinction], ADDITION, change_message="Added from a table (#3709)"
            )
            created += 1
    return created


def _render(request: HttpRequest, **context: object) -> HttpResponse:
    base = {
        "title": "Add distinctions from a table",
        "columns": COLUMNS,
        "text": "",
        "rows": None,
        "digest": "",
        "counts": None,
        "needs_setup": False,
    }
    base.update(context)
    return render(request, "admin/distinction_builder/paste.html", base)


@superuser_required
def distinction_paste(request: HttpRequest) -> HttpResponse:
    """GET the form; POST ``action=check`` previews; POST ``action=create`` writes.

    A create POST re-parses the pasted text and refuses when its digest no longer
    matches the preview's (the text or the database changed in between), when any
    row reads error, or when the operator has no linked contributor to credit.
    """
    contributor = current_contributor(request.user)
    if request.method != "POST":
        return _render(request, needs_setup=contributor is None)
    text = request.POST.get("text", "")
    rows = parse_table(text)
    counts = {
        STATUS_CREATE: sum(r.status == STATUS_CREATE for r in rows),
        STATUS_SKIP: sum(r.status == STATUS_SKIP for r in rows),
        STATUS_ERROR: sum(r.status == STATUS_ERROR for r in rows),
    }
    digest = table_digest(rows)
    action = request.POST.get("action", ACTION_CHECK)
    if action != ACTION_CREATE:
        return _render(request, text=text, rows=rows, digest=digest, counts=counts)
    if contributor is None:
        messages.error(request, "Link a contributor before adding distinctions.")
        return _render(
            request, text=text, rows=rows, digest=digest, counts=counts, needs_setup=True
        )
    if not hmac.compare_digest(digest, request.POST.get("digest", "")):
        messages.error(
            request, "The table or the database changed since the preview; check it again."
        )
        return _render(request, text=text, rows=rows, digest=digest, counts=counts)
    if counts[STATUS_ERROR]:
        messages.error(request, "Fix every row that reads error; nothing was created.")
        return _render(request, text=text, rows=rows, digest=digest, counts=counts)
    if not counts[STATUS_CREATE]:
        messages.info(request, "Nothing to create.")
        return _render(request, text=text, rows=rows, digest=digest, counts=counts)
    created = _create_rows(rows, contributor, request.user.pk)
    messages.success(request, f"Created {created} distinction(s), credited to you.")
    return redirect(reverse("admin:arxii_distinction_changelist"))
