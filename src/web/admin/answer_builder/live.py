"""The Answer builder's read-only context (#4333 slice 3): computed from the saved
rows, never written.

* the coverage grid: pledge type (and "no pledge type") by outcome tier, with a
  count of active answers in each cell;
* what each linked row is: a clue's kind, mode and target, a cost pool's
  consequences at the answer's tier;
* a preview of the vision the saved answer sends;
* the being's worship numbers, the page's checks and the answer's credit.
"""

from __future__ import annotations

from dataclasses import dataclass

from world.ceremonies.models import CeremonyOffering
from world.clues.constants import ClueTargetKind
from world.traits.models import CheckOutcome
from world.worship.answer_services import (
    answer_body,
    answer_footnotes,
    carries_fact,
)
from world.worship.constants import BeingResonanceTier
from world.worship.models import (
    Answer,
    BeingResonance,
    PendingAnswer,
    Pledge,
    Vision,
    WorshippedBeing,
)

#: The coverage row for answers with no pledge type (the being's general answers).
NO_PLEDGE = "none"
#: The sacrificed item the preview shows with the being's first favored facet.
PREVIEW_ITEM_NAME = "[a sacrificed item]"


def tiers() -> list[CheckOutcome]:
    """Every outcome tier, lowest first, as the coverage grid's columns."""
    return list(CheckOutcome.objects.order_by("success_level", "name"))


@dataclass(frozen=True)
class CoverageCell:
    tier: CheckOutcome
    count: int
    url: str
    current: bool


@dataclass(frozen=True)
class CoverageRow:
    label: str
    key: str
    cells: list[CoverageCell]


def coverage(
    being: WorshippedBeing,
    columns: list[CheckOutcome],
    *,
    cell_url,
    current: tuple[str, int | None],
) -> list[CoverageRow]:
    """The grid: one row for the being's general answers, then one per pledge type."""
    counts: dict[tuple[str, int], int] = {}
    for answer in Answer.objects.filter(being=being, is_active=True):
        key = (str(answer.pledge_id) if answer.pledge_id else NO_PLEDGE, answer.outcome_tier_id)
        counts[key] = counts.get(key, 0) + 1
    scopes = [("No pledge type (live answers)", NO_PLEDGE)] + [
        (f"Pledge type: {pledge.name}", str(pledge.pk))
        for pledge in Pledge.objects.filter(being=being).order_by("pk")
    ]
    rows = []
    for label, key in scopes:
        cells = [
            CoverageCell(
                tier=tier,
                count=counts.get((key, tier.pk), 0),
                url=cell_url(key, tier.pk),
                current=(key, tier.pk) == current,
            )
            for tier in columns
        ]
        rows.append(CoverageRow(label=label, key=key, cells=cells))
    return rows


def answers_for_pledge_row(being: WorshippedBeing, pledge: Pledge | None) -> dict[int, int]:
    """Active answer counts by outcome tier pk for one coverage row."""
    counts: dict[int, int] = {}
    for tier_id in Answer.objects.filter(being=being, pledge=pledge, is_active=True).values_list(
        "outcome_tier_id", flat=True
    ):
        counts[tier_id] = counts.get(tier_id, 0) + 1
    return counts


def tiers_written(pledge: Pledge) -> int:
    """How many outcome tiers have at least one active answer for ``pledge``."""
    return (
        Answer.objects.filter(pledge=pledge, is_active=True)
        .values("outcome_tier")
        .distinct()
        .count()
    )


# ---------------------------------------------------------------------------
# What a linked row is
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Linked:
    title: str
    detail: str


def clue_context(clue) -> Linked | None:
    """A clue's name, kind and mode, and what finding it hands over."""
    if clue is None:
        return None
    title = f"{clue.name} · {clue.get_target_kind_display()} · {clue.get_resolution_mode_display()}"
    kind = clue.target_kind
    if kind == ClueTargetKind.CODEX and clue.target_codex_entry is not None:
        entry = clue.target_codex_entry
        reach = entry.clues.count()
        visibility = "public" if entry.is_public else "not public"
        detail = f"Grants the codex entry {entry.name}, which is {visibility}"
        if reach:
            detail += f" and is reached by {reach} clue{'s' if reach != 1 else ''}"
        return Linked(title=title, detail=detail + ".")
    if kind == ClueTargetKind.MISSION and clue.target_mission is not None:
        mission = clue.target_mission
        nodes = mission.nodes.count()
        return Linked(
            title=title,
            detail=f"Assigns the mission {mission} ({nodes} node{'s' if nodes != 1 else ''}).",
        )
    if kind == ClueTargetKind.SECRET:
        return Linked(title=title, detail="Grants the knowledge of a secret.")
    return Linked(title=title, detail=f"Points at a {clue.get_target_kind_display().lower()}.")


def pool_context(answer: Answer) -> Linked | None:
    """A cost pool's name, size, and the consequences it fires at this answer's tier."""
    pool = answer.cost_pool
    if pool is None:
        return None
    from world.checks.consequence_resolution import resolve_pool_consequences  # noqa: PLC0415

    consequences = resolve_pool_consequences(pool)
    at_tier = [c for c in consequences if c.outcome_tier_id == answer.outcome_tier_id]
    count = len(consequences)
    title = f"{pool.name}: {count} consequence{'s' if count != 1 else ''}"
    if not at_tier:
        return Linked(title=title, detail="None at this tier: the cost text alone is sent.")
    labels = []
    for consequence in at_tier:
        effects = ", ".join(
            effect.condition_template.name
            if effect.condition_template_id is not None
            else effect.get_effect_type_display()
            for effect in consequence.effects.select_related("condition_template")
        )
        labels.append(f"{consequence.label} ({effects})" if effects else consequence.label)
    return Linked(title=title, detail="At this tier: " + "; ".join(labels) + ".")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Preview:
    body: str
    footnotes: list[str]
    facet_name: str


def preview(answer: Answer) -> Preview | None:
    """The vision the saved answer sends, with one sacrifice of the being's first
    favored facet."""
    if answer.pk is None:
        return None
    facet_row = answer.being.being_facets.select_related("facet").order_by("facet__name").first()
    offerings = []
    if facet_row is not None:
        offerings.append(CeremonyOffering(item_name=PREVIEW_ITEM_NAME, facet=facet_row.facet))
    return Preview(
        body=answer_body(answer, offerings),
        footnotes=list(answer_footnotes(answer)),
        facet_name=facet_row.facet.name if facet_row is not None else "",
    )


# ---------------------------------------------------------------------------
# Rail
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorshipStats:
    favored: int
    associated: int
    favored_facets: str
    rites: int
    held_answers: int


def worship_stats(being: WorshippedBeing) -> WorshipStats:
    tiers_held = list(BeingResonance.objects.filter(being=being).values_list("tier", flat=True))
    return WorshipStats(
        favored=tiers_held.count(BeingResonanceTier.FAVORED),
        associated=tiers_held.count(BeingResonanceTier.ASSOCIATED),
        favored_facets=", ".join(sorted(being.being_facets.values_list("facet__name", flat=True))),
        rites=being.rites.count(),
        held_answers=PendingAnswer.objects.filter(answer__being=being).count(),
    )


def times_used(answer: Answer) -> int:
    return Vision.objects.filter(answer=answer).count() if answer.pk else 0


def _fallback_label(
    tier: CheckOutcome, row_counts: dict[int, int], general: dict[int, int], columns
) -> str:
    if general.get(tier.pk) and row_counts is not general:
        return f"{tier.name} uses the being's general {tier.name} answer."
    for lower in sorted(
        (t for t in columns if t.success_level < tier.success_level),
        key=lambda t: t.success_level,
        reverse=True,
    ):
        if row_counts.get(lower.pk) or general.get(lower.pk):
            return f"{tier.name} uses {lower.name}."
    return f"A close at {tier.name} sends no vision; the closing award still lands."


def _fact_checks(answer: Answer) -> list[tuple[str, str]]:
    """The tier's fact rule, and whether a codex fact is really hidden."""
    tier = answer.outcome_tier
    if not carries_fact(answer):
        return [("ok", f"No fact on {tier.name}: facts are given on Success and above only.")]
    lines: list[tuple[str, str]] = []
    clue = answer.fact_clue if answer.fact_clue_id is not None else None
    if clue is not None:
        lines.append(
            ("ok", f"Fact clue on {tier.name} (allowed on Success and Critical Success only).")
        )
    entry = clue.target_codex_entry if clue and clue.target_kind == ClueTargetKind.CODEX else None
    if entry is not None and entry.is_public:
        lines.append(("warn", "The fact clue's codex entry is public: the fact is no secret."))
    elif entry is not None:
        lines.append(("ok", "The clue's target is reachable only through clues."))
    return lines


def checks(
    answer: Answer, pledge: Pledge | None, columns: list[CheckOutcome]
) -> list[tuple[str, str]]:
    """("ok" | "warn", text) lines about the saved rows. Warnings never block a save."""
    lines = _fact_checks(answer)
    if answer.pk is not None and not answer.delay_text.strip():
        lines.append(("warn", "No delay text: the vision opens without acknowledging the effort."))
    being = answer.being
    row_counts = answers_for_pledge_row(being, pledge)
    general = answers_for_pledge_row(being, None)
    for column in columns:
        if row_counts.get(column.pk):
            continue
        lines.append(
            (
                "warn",
                f"No {column.name} answer. {_fallback_label(column, row_counts, general, columns)}",
            )
        )
    return lines


@dataclass(frozen=True)
class CreditSummary:
    written: str
    reviewed: str


def credit_summary(answer: Answer) -> CreditSummary:
    """Who wrote and reviewed the answer open on the page."""
    if answer.pk is None:
        return CreditSummary(written="Not yet written", reviewed="Not yet reviewed")
    return CreditSummary(
        written=answer.written_by.name if answer.written_by_id else "Not yet written",
        reviewed=answer.reviewed_by.name if answer.reviewed_by_id else "Not yet reviewed",
    )
