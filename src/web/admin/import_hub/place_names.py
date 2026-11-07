"""Place names from a table (#5001): additions-only entry of a culture's place-name bank.

Staff paste one row per name, ``culture | name | weight``; the view resolves the culture
against the cultures that exist, previews each row as create, skip or error, and a
digest-guarded confirm creates the entries in one transaction. The rules are the paste
scaffold's (``web.admin.paste_common``): a name that already is a place name on that
culture is skipped, never updated; a culture that does not exist is an error, never
created (make it in the admin first); nothing is deleted. Place names carry no author
credit: ``NameCulture`` and ``NameCultureEntry`` are not credited content.

This is how the banks reach production. ``world.seeds.place_names`` loads them on an
empty database; here the owner's edited text lands only its missing rows.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac

from django.contrib import messages
from django.contrib.admin.models import ADDITION, LogEntry
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.identifier_dashes import contains_dash
from web.admin.paste_common import (
    ACTION_CHECK,
    ACTION_CREATE,
    STATUS_CREATE,
    STATUS_ERROR,
    PasteRow,
    counts as _counts,
    digest_of,
    one,
)
from web.admin.tuning.views import superuser_required
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.societies.houses.models import Title

COLUMNS: tuple[str, ...] = ("culture", "name", "weight")
_NO_NAME = "no name"
_DASH_NOTE = "names use a hyphen, not a dash"
MAX_WEIGHT = 1000
MAX_NAME = 100
_WEIGHT_NOTE = f"weight is a whole number from 1 to {MAX_WEIGHT}"
_LONG_NAME_NOTE = f"names are at most {MAX_NAME} characters"
_TITLE_NOTE = "a title bears this name; the layout tool will skip it"


@dataclass
class RowSpec(PasteRow):
    culture_name: str = ""
    name: str = ""
    weight: int = 1
    culture_id: int | None = None
    culture_label: str = ""

    @property
    def will_create(self) -> str:
        return f"Place name on {self.culture_label}, weight {self.weight}"


def _parse_weight(raw: str, row: RowSpec) -> int:
    raw = raw.strip()
    if not raw:
        return 1
    try:
        weight = int(raw)
    except ValueError:
        row.fail(f"{_WEIGHT_NOTE}, not {raw!r}")
        return 1
    if weight < 1 or weight > MAX_WEIGHT:
        row.fail(f"{_WEIGHT_NOTE}, not {raw!r}")
        return 1
    return weight


def _parse_row(line_no: int, fields: list[str]) -> RowSpec:
    cells = [f.strip() for f in fields] + [""] * (len(COLUMNS) - len(fields))
    row = RowSpec(line_no=line_no, culture_name=cells[0], name=cells[1])
    culture, why = one(NameCulture.objects.filter(name__iexact=row.culture_name), "culture")
    if culture is None:
        row.fail(why)
    else:
        row.culture_id = culture.pk
        row.culture_label = culture.name
    if not row.name:
        row.fail(_NO_NAME)
    elif len(row.name) > MAX_NAME:
        row.fail(_LONG_NAME_NOTE)
    elif contains_dash(row.name):
        row.fail(_DASH_NOTE)
    row.weight = _parse_weight(cells[2], row)
    if row.status != STATUS_CREATE:
        return row
    existing = (
        NameCultureEntry.objects.filter(
            culture_id=row.culture_id, part=NamePart.PLACE, value__iexact=row.name
        )
        .values_list("value", flat=True)
        .first()
    )
    if existing is not None:
        row.skip(f"already a place name on this culture, as {existing!r}")
    elif Title.objects.filter(name=row.name).exists():
        row.notes.append(_TITLE_NOTE)
    return row


def parse_table(text: str) -> list[RowSpec]:
    """Every non-blank line of ``text`` as a ``RowSpec``, resolved against the database."""
    rows: list[RowSpec] = []
    seen: set[tuple[int | None, str]] = set()
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.count("|") == 0:
            row = RowSpec(line_no=line_no, name=line.strip()[:MAX_NAME])
            row.fail("no pipe-separated columns")
            rows.append(row)
            continue
        row = _parse_row(line_no, line.split("|"))
        key = (row.culture_id, row.name.lower())
        if row.status == STATUS_CREATE and key in seen:
            row.skip("appears earlier in this table")
        seen.add(key)
        rows.append(row)
    return rows


def table_digest(rows: list[RowSpec]) -> str:
    """A digest of exactly what the preview showed: rows, resolved cultures, statuses."""
    return digest_of([(r.line_no, r.culture_id, r.name, r.weight, r.status) for r in rows])


def _create_rows(rows: list[RowSpec], user_id: int) -> int:
    """Create every ``create`` row's entry; one transaction, one log line per culture."""
    created = 0
    per_culture: dict[int, int] = {}
    with transaction.atomic():
        for row in rows:
            if row.status != STATUS_CREATE or row.culture_id is None:
                continue
            NameCultureEntry.objects.create(
                culture_id=row.culture_id, part=NamePart.PLACE, value=row.name, weight=row.weight
            )
            per_culture[row.culture_id] = per_culture.get(row.culture_id, 0) + 1
            created += 1
        for culture_id, count in per_culture.items():
            LogEntry.objects.log_actions(
                user_id,
                [NameCulture.objects.get(pk=culture_id)],
                ADDITION,
                change_message=f"Added {count} place names from a table (#5001)",
            )
    return created


def _render(request: HttpRequest, **context: object) -> HttpResponse:
    base = {
        "title": "Add place names from a table",
        "columns": COLUMNS,
        "text": "",
        "rows": None,
        "digest": "",
        "counts": None,
    }
    base.update(context)
    return render(request, "admin/import_hub/place_names.html", base)


@superuser_required
def place_name_paste(request: HttpRequest) -> HttpResponse:
    """GET the form; POST ``action=check`` previews; POST ``action=create`` writes."""
    if request.method != "POST":
        return _render(request)
    text = request.POST.get("text", "")
    rows = parse_table(text)
    counts = _counts(rows)
    digest = table_digest(rows)
    action = request.POST.get("action", ACTION_CHECK)
    if action != ACTION_CREATE:
        return _render(request, text=text, rows=rows, digest=digest, counts=counts)
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
    created = _create_rows(rows, request.user.pk)
    messages.success(request, f"Created {created} place name(s).")
    return redirect(reverse("admin:arxii_nameculture_changelist"))
