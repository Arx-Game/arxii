"""Fall / Redemption service functions (#1583).

- ``grant_compromise_resonance`` — grants non-native resonance from a
  compromising act (thin wrapper over ``grant_resonance``).
- ``perform_fall`` — the full Fall/Redemption conversion ceremony.
- ``get_fall_redemption_config`` — lazy-create singleton (re-exported from
  conversion.py for convenience).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import GainSource
from world.magic.exceptions import FallEligibilityError
from world.magic.models.aura import CharacterAura
from world.magic.models.fall_redemption import (
    ConversionType,
    FallRedemptionRecord,
)
from world.magic.services.conversion import (
    ConversionResult,
    convert_resonance,
    get_fall_redemption_config,
)
from world.magic.services.resonance import grant_resonance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.fall_redemption import CompromiseActType

# Affinity name constants (lower-case for comparison)
_CELESTIAL = "celestial"
_PRIMAL = "primal"
_ABYSSAL = "abyssal"

# The affinity ordering: lower = "higher" (more redeemable)
_AFFINITY_RANK = {_CELESTIAL: 0, _PRIMAL: 1, _ABYSSAL: 2}


def grant_compromise_resonance(
    character_sheet: CharacterSheet,
    act_type: CompromiseActType,
) -> object:
    """Grant non-native resonance from a compromising act.

    Thin wrapper over ``grant_resonance`` with ``source=GainSource.COMPROMISE``.
    Aura drifts automatically via ``recompute_aura``.

    Args:
        character_sheet: The character performing the compromising act.
        act_type: The authored act type (carries target_resonance + amount).

    Returns:
        The updated CharacterResonance instance.
    """
    return grant_resonance(
        character_sheet,
        act_type.target_resonance,
        act_type.amount,
        source=GainSource.COMPROMISE,
    )


@dataclass(frozen=True)
class FallResult:
    """Frozen result of a Fall/Redemption conversion ceremony."""

    conversion_result: ConversionResult
    conversion_type: ConversionType
    from_affinity: str
    to_affinity: str
    record_id: int


@transaction.atomic
def perform_fall(
    character_sheet: CharacterSheet,
    *,
    target_affinity: str,
    scene: object | None = None,
) -> FallResult:
    """Perform the full Fall/Redemption conversion ceremony.

    Converts ALL of the character's resonance balances, threads, and claimed
    resonances from their current dominant affinity to the target affinity.
    Irreversible — a ``FallRedemptionRecord`` is created.

    Gates:
    1. The character's aura must have the target affinity >= fall_threshold_percent.
    2. The character must not have already undergone this exact conversion.

    Args:
        character_sheet: The character undergoing the Fall/Redemption.
        target_affinity: The destination affinity ("primal", "abyssal",
            "celestial"). A Fall goes down (Celestial→Primal→Abyssal);
            Redemption goes up.
        scene: Optional scene FK for the audit record.

    Returns:
        FallResult with conversion details.

    Raises:
        FallEligibilityError: if aura threshold not met or already converted.
    """
    config = get_fall_redemption_config()

    # Resolve current dominant affinity from CharacterAura
    try:
        aura = CharacterAura.objects.get(character=character_sheet.character)
    except CharacterAura.DoesNotExist as exc:
        msg = "This character has no aura — they are not magically active."
        raise FallEligibilityError(msg) from exc

    dominant = aura.dominant_affinity  # AffinityType enum
    from_affinity = dominant.value  # "celestial", "primal", "abyssal"

    # Gate 1: target affinity must have crossed the threshold
    target_percent = getattr(aura, target_affinity, Decimal(0))
    if target_percent < config.fall_threshold_percent:
        msg = (
            f"Your {target_affinity} affinity is only {target_percent}%; "
            f"you must reach {config.fall_threshold_percent}% to convert."
        )
        raise FallEligibilityError(msg)

    # Can't convert to the same affinity
    if from_affinity == target_affinity:
        msg = f"You are already dominant in {target_affinity}."
        raise FallEligibilityError(msg)

    # Gate 2: irreversibility — check for existing record
    if FallRedemptionRecord.objects.filter(
        character_sheet=character_sheet,
        from_affinity=from_affinity,
        to_affinity=target_affinity,
    ).exists():
        msg = "You have already undergone this conversion."
        raise FallEligibilityError(msg)

    # Determine conversion type (Fall = going down, Redemption = going up)
    from_rank = _AFFINITY_RANK.get(from_affinity, 1)
    to_rank = _AFFINITY_RANK.get(target_affinity, 1)
    conversion_type = ConversionType.FALL if to_rank > from_rank else ConversionType.REDEMPTION

    # Get the multiplier for this path
    from world.magic.services.conversion import _get_multiplier  # noqa: PLC0415

    multiplier = _get_multiplier(config, from_affinity, target_affinity)

    # Perform the conversion
    result = convert_resonance(
        character_sheet,
        source_affinity=from_affinity,
        target_affinity=target_affinity,
        multiplier=multiplier,
        partial=False,
    )

    # Create the irreversibility record
    record = FallRedemptionRecord.objects.create(
        character_sheet=character_sheet,
        conversion_type=conversion_type,
        from_affinity=from_affinity,
        to_affinity=target_affinity,
        multiplier=multiplier,
        scene=scene,
    )

    return FallResult(
        conversion_result=result,
        conversion_type=conversion_type,
        from_affinity=from_affinity,
        to_affinity=target_affinity,
        record_id=record.pk,
    )
