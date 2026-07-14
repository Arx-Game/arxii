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
    from world.magic.services.conversion import ConversionResult


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
    """Target's corruption stage for the resonance is above 2."""


class AtonementNothingToAtone(AtonementError):
    """No corruption to reduce AND no non-native resonance to convert."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

# Amount reduced per successful Atonement (authored value, tuning surface).
ATONEMENT_REDUCE_AMOUNT: int = 100

# Affinity names (lower-case) used for gate checks.
_ABYSSAL_AFFINITY_NAME: str = "abyssal"
_FALLBACK_AFFINITY_NAME: str = "primal"
_CELESTIAL_AFFINITY_NAME: str = "celestial"
_MAX_ATONEMENT_STAGE: int = 2


@dataclass(frozen=True)
class AtonementResult:
    """Frozen result returned by perform_atonement_rite on success.

    Extended in #1583 to carry resonance-conversion details alongside the
    existing corruption-reduction details. A single Atonement may perform
    one or both effects independently.
    """

    performer_sheet_id: int
    resonance_id: int
    stage_before: int
    stage_after: int
    amount_reduced: int
    condition_resolved: bool
    # #1583 — resonance conversion (Effect 2). None when no conversion happened.
    resonance_conversion: ConversionResult | None = None


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------


def _get_dominant_affinity_name(performer_sheet: CharacterSheet) -> str:
    """Return the dominant affinity name (lower-case) for a character sheet.

    Reads the performer's stored CharacterAura; falls back to 'primal' if the
    sheet has no CharacterAura row (not magically active — treat as non-Abyssal
    so the gate is not accidentally over-restrictive for data-incomplete sheets).
    """
    from world.magic.services.resonance_environment import magical_profile  # noqa: PLC0415

    aura = magical_profile(performer_sheet)
    if aura is None:
        return _FALLBACK_AFFINITY_NAME  # safe neutral fallback
    return aura.dominant_affinity


def perform_atonement_rite(  # noqa: C901
    *,
    performer_sheet: CharacterSheet,
    target_sheet: CharacterSheet,
    resonance: Resonance,
    penance_amount: int | None = None,
) -> AtonementResult:
    """Perform the Rite of Atonement: cleanse corruption AND/OR convert drift.

    Extended in #1583 to perform two complementary effects:

    **Effect 1 (existing): Corruption reduction.** If the performer has
    corruption at stage 1–2 on the specified resonance, calls
    ``reduce_corruption``. Skipped when corruption is at stage 0 or no
    condition exists. Stage 3+ still raises ``AtonementStageOutOfRange``.

    **Effect 2 (new): Resonance conversion.** If the performer's dominant
    affinity is Celestial and they have non-native (Primal/Abyssal) resonance
    balance > 0, converts a portion back to Celestial at the lossy penance
    exchange rate. The player may specify how much to convert via
    ``penance_amount``; None = all non-native balance.

    At least one effect must fire, or ``AtonementNothingToAtone`` is raised.

    Gates (in order):
    1. Performer's dominant affinity must not be Abyssal.
    2. Target must be performer (self-targeting only).
    3. If corruption stage > 2: raise (use Soul Tether rescue for advanced).
       If corruption stage in (0, None): skip Effect 1.
       If corruption stage in (1, 2): fire Effect 1.
    4. If Celestial and non-native balance > 0: fire Effect 2.

    Args:
        performer_sheet: CharacterSheet of the character performing the rite.
        target_sheet: CharacterSheet of the target (must equal performer_sheet).
        resonance: The Resonance whose corruption is being cleansed (Effect 1).
        penance_amount: For Effect 2: how much non-native balance to convert.
            None = convert all non-native balance.

    Returns:
        AtonementResult frozen dataclass.

    Raises:
        AtonementAffinityRefused: if performer is Abyssal-dominant.
        AtonementSelfTargetRequired: if target != performer.
        AtonementStageOutOfRange: if corruption stage > 2.
        AtonementNothingToAtone: if neither effect is applicable.
    """
    from world.magic.exceptions import ConversionMappingError  # noqa: PLC0415
    from world.magic.services.conversion import (  # noqa: PLC0415
        convert_resonance,
        get_fall_redemption_config,
    )

    # --- Gate 1: affinity check ---
    dominant = _get_dominant_affinity_name(performer_sheet)
    if dominant == _ABYSSAL_AFFINITY_NAME:
        msg = "The Rite of Atonement cannot be led by a soul whose primary affinity is Abyssal."
        raise AtonementAffinityRefused(msg)

    # --- Gate 2: self-target ---
    if performer_sheet.pk != target_sheet.pk:
        msg = "The Rite of Atonement requires the performer to be their own target."
        raise AtonementSelfTargetRequired(msg)

    # --- Gate 3: corruption stage (conditional) ---
    stage = target_sheet.get_corruption_stage(resonance)
    if stage > _MAX_ATONEMENT_STAGE:
        msg = (
            f"The Rite of Atonement cannot cleanse corruption at stage "
            f"{stage} (use Soul Tether rescue)."
        )
        raise AtonementStageOutOfRange(msg)

    # --- Effect 1: corruption reduction (stages 1-2 only) ---
    from world.magic.services.corruption import reduce_corruption  # noqa: PLC0415
    from world.magic.types.corruption import CorruptionRecoverySource  # noqa: PLC0415

    corruption_result = None
    if stage in (1, _MAX_ATONEMENT_STAGE):
        corruption_result = reduce_corruption(
            character_sheet=target_sheet,
            resonance=resonance,
            amount=ATONEMENT_REDUCE_AMOUNT,
            source=CorruptionRecoverySource.ATONEMENT_RITE,
        )

    # --- Effect 2: resonance conversion (Celestial with non-native balance) ---
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    resonance_conversion = None
    if dominant == _CELESTIAL_AFFINITY_NAME:
        # Find non-native resonance rows with balance > 0
        non_native_rows = CharacterResonance.objects.filter(
            character_sheet=performer_sheet,
            balance__gt=0,
        ).exclude(resonance__affinity__name__iexact=_CELESTIAL_AFFINITY_NAME)

        # Exclude rows that are already Celestial — only convert non-native.
        # Also exclude the resonance being atoned for from the conversion
        # if it's already Celestial (it is, since Effect 1 targets corruption
        # on a potentially non-Celestial resonance).
        non_native_rows = non_native_rows.select_related("resonance__affinity")

        if non_native_rows.exists():
            config = get_fall_redemption_config()
            # Convert each non-native affinity's resonance back to Celestial
            # For simplicity, group by source affinity and convert each
            converted_results = []
            seen_affinities = set()
            for cr in non_native_rows:
                source_affinity = cr.resonance.affinity.name.lower()
                if source_affinity in seen_affinities:
                    continue
                seen_affinities.add(source_affinity)
                try:
                    result = convert_resonance(
                        performer_sheet,
                        source_affinity=source_affinity,
                        target_affinity=_CELESTIAL_AFFINITY_NAME,
                        multiplier=config.penance_exchange_rate,
                        partial=True,
                        penance_amount=penance_amount,
                    )
                    converted_results.append(result)
                except ConversionMappingError:
                    # No ResonanceConversion mapping exists for this
                    # (source_resonance, celestial) pair — skip this affinity.
                    pass
            if converted_results:
                # Return the first conversion result (there should typically
                # be one — either Primal or Abyssal, rarely both)
                resonance_conversion = converted_results[0]

    # --- At least one effect must fire ---
    if corruption_result is None and resonance_conversion is None:
        msg = (
            "There is nothing to atone for — no corruption and no non-native resonance to convert."
        )
        raise AtonementNothingToAtone(msg)

    return AtonementResult(
        performer_sheet_id=performer_sheet.pk,
        resonance_id=resonance.pk,
        stage_before=corruption_result.stage_before if corruption_result else stage,
        stage_after=corruption_result.stage_after if corruption_result else stage,
        amount_reduced=corruption_result.amount_reduced if corruption_result else 0,
        condition_resolved=corruption_result.condition_resolved if corruption_result else False,
        resonance_conversion=resonance_conversion,
    )
