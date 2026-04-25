"""Atonement Rite service — Scope #7 Phase 8 (SERVICE dispatch).

The Rite of Atonement is dispatched via execution_kind=SERVICE, invoking
``world.magic.services.atonement.perform_atonement_rite``.  The service
performs all eligibility checks and, on success, calls reduce_corruption.

**Deviation from spec §4.1:** spec recommends FLOW dispatch.  SERVICE
dispatch is used here because the flow step vocabulary has no native
"check performer affinity is in (Celestial, Primal)" step — doing so via
CALL_SERVICE_FUNCTION + EVALUATE_EQUALS would require an additional thin
wrapper service anyway.  SERVICE dispatch keeps the gate logic in one
auditable place and is explicitly listed as an acceptable deviation in the
implementation plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Resonance


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class AtonementError(Exception):
    """Base for all Atonement Rite refusals.

    Carries a ``user_message`` safe for display; callers surface this to the
    player rather than the raw exception string.
    """

    user_message: str

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class AtonementAffinityRefused(AtonementError):
    """Performer's dominant affinity is Abyssal — Atonement is refused."""


class AtonementSelfTargetRequired(AtonementError):
    """Performer and target must be the same CharacterSheet."""


class AtonementStageOutOfRange(AtonementError):
    """Target's corruption stage for the resonance is not in (1, 2)."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

# Amount reduced per successful Atonement (authored value, tuning surface).
ATONEMENT_REDUCE_AMOUNT: int = 100

# Affinity names (lower-case) used for gate checks.
_ABYSSAL_AFFINITY_NAME: str = "abyssal"
_FALLBACK_AFFINITY_NAME: str = "primal"


@dataclass(frozen=True)
class AtonementResult:
    """Frozen result returned by perform_atonement_rite on success."""

    performer_sheet_id: int
    resonance_id: int
    stage_before: int
    stage_after: int
    amount_reduced: int
    condition_resolved: bool


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------


def _get_dominant_affinity_name(performer_sheet: CharacterSheet) -> str:
    """Return the dominant affinity name (lower-case) for a character sheet.

    Reads CharacterAffinityTotal rows; falls back to 'primal' if no rows
    exist (neutral character without affinity data — treat as non-Abyssal
    so gate is not accidentally over-restrictive for data-incomplete sheets).
    """
    from world.magic.models.aura import CharacterAffinityTotal  # noqa: PLC0415

    totals = list(
        CharacterAffinityTotal.objects.filter(character=performer_sheet).select_related("affinity")
    )
    if not totals:
        return _FALLBACK_AFFINITY_NAME  # safe neutral fallback
    dominant = max(totals, key=lambda t: t.total)
    return dominant.affinity.name.lower()


def perform_atonement_rite(
    *,
    performer_sheet: CharacterSheet,
    target_sheet: CharacterSheet,
    resonance: Resonance,
) -> AtonementResult:
    """Perform the Rite of Atonement: gate-check and call reduce_corruption.

    Gates (in order):
    1. Performer's dominant affinity must be Celestial or Primal (not Abyssal).
    2. Target must be performer (self-targeting only in foundation).
    3. Target's corruption stage on *resonance* must be in (1, 2).

    On success: calls reduce_corruption with source=ATONEMENT_RITE and
    amount=ATONEMENT_REDUCE_AMOUNT.

    Args:
        performer_sheet: CharacterSheet of the character performing the rite.
        target_sheet: CharacterSheet of the target (must equal performer_sheet).
        resonance: The Resonance whose corruption is being cleansed.

    Returns:
        AtonementResult frozen dataclass.

    Raises:
        AtonementAffinityRefused: if performer is Abyssal-dominant.
        AtonementSelfTargetRequired: if target != performer.
        AtonementStageOutOfRange: if corruption stage not in (1, 2).
    """
    from world.magic.services.corruption import reduce_corruption  # noqa: PLC0415
    from world.magic.types.corruption import CorruptionRecoverySource  # noqa: PLC0415

    # --- Gate 1: affinity check ---
    dominant = _get_dominant_affinity_name(performer_sheet)
    if dominant == _ABYSSAL_AFFINITY_NAME:
        msg = "The Rite of Atonement cannot be led by a soul whose primary affinity is Abyssal."
        raise AtonementAffinityRefused(msg)

    # --- Gate 2: self-target ---
    if performer_sheet.pk != target_sheet.pk:
        msg = "The Rite of Atonement requires the performer to be their own target."
        raise AtonementSelfTargetRequired(msg)

    # --- Gate 3: stage in (1, 2) ---
    stage = target_sheet.get_corruption_stage(resonance)
    if stage not in (1, 2):
        msg = f"The Rite of Atonement requires corruption at stage 1 or 2 (current stage: {stage})."
        raise AtonementStageOutOfRange(msg)

    # --- Effect ---
    result = reduce_corruption(
        character_sheet=target_sheet,
        resonance=resonance,
        amount=ATONEMENT_REDUCE_AMOUNT,
        source=CorruptionRecoverySource.ATONEMENT_RITE,
    )

    return AtonementResult(
        performer_sheet_id=performer_sheet.pk,
        resonance_id=resonance.pk,
        stage_before=result.stage_before,
        stage_after=result.stage_after,
        amount_reduced=result.amount_reduced,
        condition_resolved=result.condition_resolved,
    )
