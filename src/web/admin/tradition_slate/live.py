"""Live checks, rail counts and the entry-line preview for the tradition slate page (#3675).

Unlike the Upbringing Builder's live panel, most of what this page checks is
about the *standard* lines (`TraditionStateLine`, `SchoolingLine`), which are
shared across every Beginning - only the slate stats, the leftover-default
count and the preview are scoped to the one Beginning the page is open on.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Case, IntegerField, Value, When

from web.admin.authoring.copy import price_text
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    DistinctionOffer,
    SchoolingLine,
    TraditionStateLine,
)

#: States whose standard line is expected to carry a drawback (#3675 spec,
#: Decision 3): a character who never had a living teacher pays for it.
_DRAWBACK_STATES = (TraditionState.SELF_TAUGHT, TraditionState.TEACHERS_GONE)

#: Preferred order for the entry-line preview: a teachers-gone line prints a
#: state the player never gets to fill in themselves, so it takes priority
#: over self-taught when a slate carries both.
_PREVIEW_STATES = (TraditionState.TEACHERS_GONE, TraditionState.SELF_TAUGHT)


@dataclass(frozen=True)
class LinePriceDisplay:
    """A standard line's derived price, plus the help text explaining where it came from."""

    text: str
    help: str


def state_line_display(line: TraditionStateLine) -> LinePriceDisplay:
    help_text = (
        f"read from {line.carries.name}'s price; edit it on its Builder page"
        if line.carries_id
        else "nothing carried, nothing to price"
    )
    return LinePriceDisplay(text=price_text(line.price), help=help_text)


def schooling_line_display(line: SchoolingLine) -> LinePriceDisplay:
    help_text = (
        f"{line.grants.name}'s per-rank price × {line.rank}"
        if line.grants_id
        else "nothing granted, nothing to price"
    )
    return LinePriceDisplay(text=price_text(line.price), help=help_text)


def rail_counts(beginning: Beginnings) -> dict[str, int]:
    """'This slate' stat tiles: how many traditions, in which states, with own wording."""
    slate = list(BeginningTradition.objects.filter(beginning=beginning))
    return {
        "traditions": len(slate),
        "self_taught": sum(1 for row in slate if row.state == TraditionState.SELF_TAUGHT),
        "teachers_gone": sum(1 for row in slate if row.state == TraditionState.TEACHERS_GONE),
        "living_masters": sum(1 for row in slate if row.state == TraditionState.LIVING_MASTERS),
        "own_wording": sum(1 for row in slate if row.own_wording),
    }


def _drawback_checks(state_lines: dict[str, TraditionStateLine]) -> list[tuple[str, str]]:
    missing = [
        state.label
        for state in _DRAWBACK_STATES
        if not (state_lines.get(state) and state_lines[state].carries_id)
    ]
    if not missing:
        return [("ok", "Every self-taught and teachers-gone line carries a drawback.")]
    return [("warn", f"'{name}' carries nothing.") for name in missing]


def _exclusion_check(state_lines: dict[str, TraditionStateLine]) -> list[tuple[str, str]]:
    self_taught = state_lines.get(TraditionState.SELF_TAUGHT)
    teachers_gone = state_lines.get(TraditionState.TEACHERS_GONE)
    if not (self_taught and self_taught.carries_id and teachers_gone and teachers_gone.carries_id):
        return []
    excluded = self_taught.carries.mutually_exclusive_with.filter(
        pk=teachers_gone.carries_id
    ).exists()
    if excluded:
        return [("ok", "The self-taught and teachers-gone drawbacks cannot be held together.")]
    return [
        (
            "warn",
            "The self-taught and teachers-gone drawbacks can be held together; "
            "see the Distinction Builder's 'Cannot be held with' chips.",
        )
    ]


def _default_state_check(beginning: Beginnings) -> list[tuple[str, str]]:
    count = BeginningTradition.objects.filter(
        beginning=beginning, state=TraditionState.LIVING_MASTERS
    ).count()
    if not count:
        return [("ok", "No slate lines are left at the default state.")]
    noun = "line" if count == 1 else "lines"
    return [("warn", f"{count} slate {noun} still at the default state (living masters).")]


def _offer_checks() -> list[tuple[str, str]]:
    """Every schooling line with a grant has its TRADITION_STEP offer row, or a warn."""
    checks: list[tuple[str, str]] = []
    for line in SchoolingLine.objects.filter(grants__isnull=False).order_by("rank"):
        has_offer = DistinctionOffer.objects.filter(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=line, is_active=True
        ).exists()
        if has_offer:
            checks.append(("ok", f"Schooling line {line.rank} ('{line.name}') has its offer."))
        else:
            checks.append(
                (
                    "warn",
                    f"Schooling line {line.rank} ('{line.name}') has no offer yet; "
                    "save this page to create it.",
                )
            )
    return checks


def _stale_offer_checks() -> list[tuple[str, str]]:
    """A schooling line with no grant should carry no active TRADITION_STEP offer.

    Saving this page already deactivates the offer the moment a grant is
    cleared (`views._sync_schooling_offers`), so this only ever fires for a
    line edited outside this page (stock admin) or a row from before that fix
    shipped.
    """
    checks: list[tuple[str, str]] = []
    for line in SchoolingLine.objects.filter(grants__isnull=True).order_by("rank"):
        stale = DistinctionOffer.objects.filter(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=line, is_active=True
        ).exists()
        if stale:
            checks.append(
                (
                    "warn",
                    f"Schooling line {line.rank} grants nothing but still has an active offer.",
                )
            )
    return checks


def checks(beginning: Beginnings) -> list[tuple[str, str]]:
    state_lines = {line.state: line for line in TraditionStateLine.objects.all()}
    result = _drawback_checks(state_lines)
    result.extend(_exclusion_check(state_lines))
    result.extend(_default_state_check(beginning))
    result.extend(_offer_checks())
    result.extend(_stale_offer_checks())
    return result


def preview_line(beginning: Beginnings) -> dict[str, object] | None:
    """The first teachers-gone or self-taught slate line, as the player would read it.

    Ranked by ``_PREVIEW_STATES``'s own priority first, then by the slate's
    ``sort_order`` - a teachers-gone line takes priority over a self-taught one
    regardless of which sits earlier on the slate (the demo's own worked
    example: Unbound at self-taught/order-0 must lose to Metallic Order at
    teachers-gone/order-2).
    """
    priority = Case(
        *(When(state=state, then=Value(index)) for index, state in enumerate(_PREVIEW_STATES)),
        output_field=IntegerField(),
    )
    slate = (
        BeginningTradition.objects.filter(beginning=beginning, state__in=_PREVIEW_STATES)
        .select_related("tradition")
        .annotate(_preview_priority=priority)
        .order_by("_preview_priority", "sort_order", "id")
        .first()
    )
    if slate is None:
        return None
    line = TraditionStateLine.objects.filter(state=slate.state).first()
    words = slate.own_wording or (line.entry_line if line is not None else "")
    refund = line.price if line is not None else 0
    return {
        "tradition": slate.tradition,
        "words": words,
        "price_text": price_text(refund),
    }
