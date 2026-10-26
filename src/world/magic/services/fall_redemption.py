"""Fall / Redemption service functions (#1583).

- ``grant_compromise_resonance`` — grants non-native resonance from a
  compromising act (thin wrapper over ``grant_resonance``).
- ``perform_fall`` — the full Fall/Redemption conversion ceremony.
- ``get_fall_redemption_config`` — lazy-create singleton (re-exported from
  conversion.py for convenience).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import GainSource
from world.magic.exceptions import ConversionMappingError, FallEligibilityError
from world.magic.models.aura import CharacterAura
from world.magic.models.fall_redemption import (
    ConversionType,
    FallRedemptionRecord,
)
from world.magic.services.conversion import (
    ConversionResult,
    conversion_pair,
    convert_resonance,
    get_fall_redemption_config,
)
from world.magic.services.resonance import grant_resonance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Affinity
    from world.magic.models.fall_redemption import CompromiseActType


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
    from_affinity: Affinity
    to_affinity: Affinity
    record_id: int


@transaction.atomic
def perform_fall(
    character_sheet: CharacterSheet,
    *,
    target_affinity: Affinity,
    scene: object | None = None,
    **_ritual_dispatch_kwargs: object,  # ritual dispatch also forwards ``ritual=``
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
        target_affinity: The destination Affinity row. Whether the path is a Fall
            or a Redemption comes from the authored ``AffinityInteraction`` pair.
        scene: Optional scene FK for the audit record.

    Returns:
        FallResult with conversion details.

    Raises:
        FallEligibilityError: if aura threshold not met, already converted, or no
            conversion is authored for the path.
    """
    config = get_fall_redemption_config()

    # Resolve current dominant affinity from CharacterAura
    try:
        aura = CharacterAura.objects.get(character=character_sheet)
    except CharacterAura.DoesNotExist as exc:
        msg = "This character has no aura — they are not magically active."
        raise FallEligibilityError(msg) from exc

    if not aura.cached_shares:
        msg = "This character has no aura — they are not magically active."
        raise FallEligibilityError(msg)
    from_affinity = aura.dominant_affinity

    # Gate 1: target affinity must have crossed the threshold
    target_percent = aura.percent_for(target_affinity)
    if target_percent < config.fall_threshold_percent:
        msg = (
            f"Your {target_affinity.name} affinity is only {target_percent}%; "
            f"you must reach {config.fall_threshold_percent}% to convert."
        )
        raise FallEligibilityError(msg)

    # Can't convert to the same affinity
    if from_affinity.pk == target_affinity.pk:
        msg = f"You are already dominant in {target_affinity.name}."
        raise FallEligibilityError(msg)

    # Gate 2: irreversibility — check for existing record
    if FallRedemptionRecord.objects.filter(
        character_sheet=character_sheet,
        from_affinity_ref=from_affinity,
        to_affinity_ref=target_affinity,
    ).exists():
        msg = "You have already undergone this conversion."
        raise FallEligibilityError(msg)

    # The authored pair carries the multiplier and whether this is a Fall or Redemption
    try:
        pair = conversion_pair(from_affinity, target_affinity)
    except ConversionMappingError as exc:
        msg = (
            f"No conversion is authored from {from_affinity.name} to "
            f"{target_affinity.name}; the ceremony cannot be performed."
        )
        raise FallEligibilityError(msg) from exc
    conversion_type = ConversionType(pair.conversion_type)
    multiplier = pair.conversion_multiplier

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
        from_affinity_ref=from_affinity,
        to_affinity_ref=target_affinity,
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
