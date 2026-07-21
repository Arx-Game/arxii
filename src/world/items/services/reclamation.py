"""Theft reclamation (#2368) — trace the ledger, then choose your genre.

The permanent ``OwnershipEvent`` ledger already records the truth; a claim
unlocks a hop-by-hop investigation over the item's REAL chain — every theft
generates its own mystery with zero hand-authoring. The trace terminates at
the current holder (who accepted the receiving-stolen-goods consent gate:
they opted into reclamation exposure). Two routes out: report to the
authorities, or take it back under reclamation standing — which belongs to
the wronged alone and never transfers with the claim.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.constants import (
    RECEIVING_STOLEN_CRIME_SCALE,
    RECEIVING_STOLEN_CRIME_SLUG,
    TRACE_BOTCH_LEVEL,
    TRACE_CHECK_TYPE_NAME,
    TRACE_CHILL_HOURS,
    ClaimOrigin,
    ClaimStatus,
    OwnershipEventType,
)
from world.items.models import (
    ClaimTraceStep,
    ItemInstance,
    OwnershipEvent,
    ReclamationClaim,
)
from world.items.services.provenance import stolen_victim

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.estates.models import EstateClaim

# Shared error message for settled-claim rejections.
_CLAIM_SETTLED_MSG = "That claim is settled."


class ReclamationError(Exception):
    """A reclamation rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def file_theft_claim(victim_sheet: CharacterSheet, item: ItemInstance) -> ReclamationClaim:
    """The victim reports the theft at discovery — the claim mints here."""
    if stolen_victim(item) != victim_sheet:
        msg = f"sheet {victim_sheet.pk} is not the provenance victim of item {item.pk}"
        raise ReclamationError(msg, user_message="You have no standing claim on that item.")
    if ReclamationClaim.objects.filter(
        item_instance=item, claimant_sheet=victim_sheet, status=ClaimStatus.OPEN
    ).exists():
        msg = f"open claim already exists for item {item.pk} / sheet {victim_sheet.pk}"
        raise ReclamationError(msg, user_message="You have already filed that claim.")
    return ReclamationClaim.objects.create(
        item_instance=item,
        claimant_sheet=victim_sheet,
        original_claimant_sheet=victim_sheet,
        origin=ClaimOrigin.VICTIM_REPORT,
    )


def open_trace_for_estate_claim(estate_claim: EstateClaim) -> ReclamationClaim:
    """An heir's settlement grievance opens the same trace (bridge, not copy)."""
    existing = ReclamationClaim.objects.filter(
        estate_claim=estate_claim, status=ClaimStatus.OPEN
    ).first()
    if existing is not None:
        return existing
    return ReclamationClaim.objects.create(
        item_instance=estate_claim.item_instance,
        claimant_sheet=estate_claim.claimant_sheet,
        original_claimant_sheet=estate_claim.claimant_sheet,
        origin=ClaimOrigin.ESTATE_SETTLEMENT,
        estate_claim=estate_claim,
    )


def assign_claim(claim: ReclamationClaim, new_claimant: CharacterSheet) -> ReclamationClaim:
    """A claim is a sellable document: the trace + lawful route move with it.

    ``original_claimant_sheet`` never moves — assignment transfers the claim,
    NOT the immunity (a bounty hunter stealing it back is still a thief).
    """
    if claim.status != ClaimStatus.OPEN:
        msg = f"claim {claim.pk} is not open"
        raise ReclamationError(msg, user_message=_CLAIM_SETTLED_MSG)
    new_claim = ReclamationClaim.objects.create(
        item_instance=claim.item_instance,
        claimant_sheet=new_claimant,
        original_claimant_sheet=claim.original_claimant_sheet,
        origin=claim.origin,
        estate_claim=claim.estate_claim,
        acquired_from=claim,
        trace_position=claim.trace_position,
    )
    claim.status = ClaimStatus.RELEASED
    claim.resolved_at = timezone.now()
    claim.save(update_fields=["status", "resolved_at"])
    for step in claim.trace_steps.all():
        ClaimTraceStep.objects.create(
            claim=new_claim,
            position=step.position,
            ownership_event=step.ownership_event,
            revealed_text=step.revealed_text,
        )
    return new_claim


# ---------------------------------------------------------------------------
# The trace — hop by hop over the real chain
# ---------------------------------------------------------------------------


def _theft_chain(claim: ReclamationClaim) -> list[OwnershipEvent]:
    """The ledger from the claim's theft forward — the mystery's spine."""
    theft = (
        OwnershipEvent.objects.filter(
            item_instance=claim.item_instance,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=claim.original_claimant_sheet,
        )
        .order_by("-created_at")
        .first()
    )
    if theft is None:
        return []
    return list(
        OwnershipEvent.objects.filter(
            item_instance=claim.item_instance,
            created_at__gte=theft.created_at,
        ).order_by("created_at")
    )


def _hop_text(event: OwnershipEvent) -> str:
    """PLACEHOLDER in-world prose for one revealed hop."""
    taker = event.to_persona_display.name if event.to_persona_display else "an unknown hand"
    kind = event.get_event_type_display().lower()
    return f"The trail shows it was {kind} — it passed to {taker}."


def advance_trace(claim: ReclamationClaim, *, check_level: int | None = None) -> dict:
    """One investigation step: a check reveals the next hop; a botch chills.

    The final hop reveals the current holder. ``check_level`` is injectable;
    live play rolls the tracing check type (degrading to success when the
    content is unseeded — the mystery floor must never hard-block).
    """
    if claim.status != ClaimStatus.OPEN:
        msg = f"claim {claim.pk} is not open"
        raise ReclamationError(msg, user_message=_CLAIM_SETTLED_MSG)
    now = timezone.now()
    if claim.trace_chilled_until and claim.trace_chilled_until > now:
        msg = f"claim {claim.pk} trace is chilled"
        raise ReclamationError(msg, user_message="The trail has gone cold — give it time.")
    chain = _theft_chain(claim)
    if claim.trace_position >= len(chain):
        return {"complete": True, "holder_revealed": True}

    level = check_level
    if level is None:
        level = _roll_trace_check(claim)
    if level <= TRACE_BOTCH_LEVEL:
        claim.trace_chilled_until = now + timedelta(hours=TRACE_CHILL_HOURS)
        claim.save(update_fields=["trace_chilled_until"])
        return {"complete": False, "chilled": True}
    if level < 0:
        return {"complete": False, "chilled": False}

    event = chain[claim.trace_position]
    ClaimTraceStep.objects.create(
        claim=claim,
        position=claim.trace_position,
        ownership_event=event,
        revealed_text=_hop_text(event),
    )
    claim.trace_position += 1
    claim.save(update_fields=["trace_position"])
    complete = claim.trace_position >= len(chain)
    return {"complete": complete, "holder_revealed": complete, "chilled": False}


def _roll_trace_check(claim: ReclamationClaim) -> int:
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    sheet = claim.claimant_sheet
    character = sheet.character if sheet is not None else None
    check_type = CheckType.objects.filter(name=TRACE_CHECK_TYPE_NAME).first()
    if character is None or check_type is None:
        return 1  # unseeded world: the floor never hard-blocks
    result = perform_check(character, check_type)
    return result.outcome.success_level if result.outcome else 0


def trace_complete(claim: ReclamationClaim) -> bool:
    chain = _theft_chain(claim)
    return bool(chain) and claim.trace_position >= len(chain)


# ---------------------------------------------------------------------------
# Route A — lawful: report the holder
# ---------------------------------------------------------------------------


def file_reclamation_accusation(claim: ReclamationClaim) -> bool:
    """Report the traced holder to the local powers — heat lands on THEM.

    Requires a completed trace (you must know who holds it). Returns whether
    heat actually minted (jurisdiction and local law decide, as ever).
    """
    _require_traced(claim)
    holder_sheet = claim.item_instance.holder_character_sheet
    if holder_sheet is None or holder_sheet == claim.original_claimant_sheet:
        msg = f"claim {claim.pk}: no reportable holder"
        raise ReclamationError(msg, user_message="There is no one to report.")
    persona = holder_sheet.primary_persona
    character = holder_sheet.character
    if persona is None or character is None or character.location is None:
        return False
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import accrue_heat, area_for_room  # noqa: PLC0415

    kind, _ = CrimeKind.objects.get_or_create(
        slug=RECEIVING_STOLEN_CRIME_SLUG, defaults={"name": "Receiving Stolen Goods"}
    )
    row = accrue_heat(
        persona=persona,
        crime_kind=kind,
        area=area_for_room(character.location),
        scale=RECEIVING_STOLEN_CRIME_SCALE,
    )
    return row is not None


def execute_lawful_seizure(claim: ReclamationClaim) -> ReclamationClaim:
    """The authorities return the item — the lawful route's terminal step.

    Caller is the enforcement outcome (staff/GM control now; the justice-case
    seizure sentence hooks here once the pipeline lands).
    """
    _require_traced(claim)
    _return_item(claim, ClaimStatus.RECOVERED_LAWFUL)
    return claim


# ---------------------------------------------------------------------------
# Route B — take it back
# ---------------------------------------------------------------------------


def has_reclamation_standing(taker_sheet: CharacterSheet, item: ItemInstance) -> bool:
    """Taking back your own is no crime — for the WRONGED party alone.

    The public predicate the theft crime-tagging consults: True only when the
    taker is the original claimant of an open claim on this item. Assignees
    and hirelings run normal theft risk.
    """
    return ReclamationClaim.objects.filter(
        item_instance=item,
        original_claimant_sheet=taker_sheet,
        status=ClaimStatus.OPEN,
    ).exists()


def record_steal_back(claim: ReclamationClaim, taker_sheet: CharacterSheet) -> ReclamationClaim:
    """The wronged takes theirs back quietly. Standing is checked, not assumed."""
    if taker_sheet != claim.original_claimant_sheet:
        msg = f"sheet {taker_sheet.pk} lacks standing on claim {claim.pk}"
        raise ReclamationError(
            msg, user_message="Taking that would be plain theft — it isn't yours to reclaim."
        )
    _require_traced(claim)
    _return_item(claim, ClaimStatus.RECOVERED_TAKEN)
    return claim


# ---------------------------------------------------------------------------
# Shared terminal
# ---------------------------------------------------------------------------


def _require_traced(claim: ReclamationClaim) -> None:
    if claim.status != ClaimStatus.OPEN:
        msg = f"claim {claim.pk} is not open"
        raise ReclamationError(msg, user_message=_CLAIM_SETTLED_MSG)
    if not trace_complete(claim):
        msg = f"claim {claim.pk} trace incomplete"
        raise ReclamationError(msg, user_message="You have not yet traced the item to its holder.")


def _return_item(claim: ReclamationClaim, status: str) -> None:
    """Owner pointer back to the claimant + a RECOVERED ledger row.

    Clears ``has_unresolved_stolen_provenance`` going forward (the victim
    re-appears as a recipient), releasing downstream holders from the
    hot-goods flag.
    """
    item = claim.item_instance
    previous_holder = item.holder_character_sheet
    item.holder_character_sheet = claim.claimant_sheet
    item.save(update_fields=["holder_character_sheet"])
    OwnershipEvent.objects.create(
        item_instance=item,
        event_type=OwnershipEventType.RECOVERED,
        from_character_sheet=previous_holder,
        to_character_sheet=claim.original_claimant_sheet,
    )
    claim.status = status
    claim.resolved_at = timezone.now()
    claim.save(update_fields=["status", "resolved_at"])
