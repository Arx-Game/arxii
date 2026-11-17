"""The Mire: corruption a Sineater carries for their Sinners (#5177).

``MireHolding.amount`` says how much of a Sineater's corruption in a resonance came from
which Sinner. These two services are the only writers of that amount. When corruption falls
for any other reason, ``reduce_corruption`` keeps the holdings within it.
"""

from __future__ import annotations

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.magic.models.affinity import Resonance
from world.magic.models.aura import CharacterResonance
from world.magic.models.soul_tether import MireHolding
from world.magic.services.corruption import (
    _apply_sineater_corruption_resistance,
    accrue_corruption,
    reduce_corruption,
)
from world.magic.types.corruption import CorruptionRecoverySource, CorruptionSource
from world.magic.types.soul_tether import MireTransfer
from world.relationships.models import CharacterRelationship


def corruption_ceiling(resonance: Resonance, max_stage: int | None) -> int | None:
    """The most corruption a character can hold in ``resonance`` and stay at ``max_stage``.

    One below the severity threshold of the stage after ``max_stage``. None when there is no
    cap to apply: ``max_stage`` is None, or the resonance has no corruption stage past it.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    if max_stage is None:
        return None
    template = ConditionTemplate.objects.filter(corruption_resonance=resonance).first()
    if template is None:
        return None
    next_stage = template.stages.filter(
        stage_order=max_stage + 1, severity_threshold__isnull=False
    ).first()
    if next_stage is None:
        return None
    return next_stage.severity_threshold - 1


def _largest_shed_arriving_within(
    sineater_sheet: CharacterSheet, resonance: Resonance, shed: int, allowed: int
) -> int:
    """The largest shed up to ``shed`` whose arrival, after resistance, is at most ``allowed``."""
    low, high = 0, shed
    while low < high:
        middle = (low + high + 1) // 2
        arrives = _apply_sineater_corruption_resistance(sineater_sheet, resonance, middle, None)
        if arrives <= allowed:
            low = middle
        else:
            high = middle - 1
    return low


@transaction.atomic
def take_on_corruption(
    *,
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    max_stage: int | None = None,
) -> MireTransfer:
    """Move up to ``amount`` of the Sinner's corruption in ``resonance`` onto the Sineater.

    The Sinner sheds through ``reduce_corruption`` (source SINEATING) without the resonance
    cleansing grants, because the Sineating roll decides what each earns. The Sineater takes
    it on through ``accrue_corruption`` (source SINEATING_CARRIED), so their resistance
    softens it, and the holding for this Sinner grows by what arrived.

    The Sinner never sheds more than they carry. ``max_stage`` caps the Sineater: their
    corruption in the resonance never reaches the threshold of the stage after it, and the
    Sinner sheds only what the Sineater can take. None means no cap.

    Raises:
        CharacterRelationship.DoesNotExist: the Sineater has no side toward this Sinner.
    """
    if amount <= 0:
        msg = f"amount must be > 0, got {amount}"
        raise ValueError(msg)
    relationship = CharacterRelationship.objects.get(source=sineater_sheet, target=sinner_sheet)

    sinner_row = CharacterResonance.objects.filter(
        character_sheet=sinner_sheet, resonance=resonance
    ).first()
    shed = min(amount, sinner_row.corruption_current if sinner_row is not None else 0)

    ceiling = corruption_ceiling(resonance, max_stage)
    if ceiling is not None and shed > 0:
        sineater_row = CharacterResonance.objects.filter(
            character_sheet=sineater_sheet, resonance=resonance
        ).first()
        carried = sineater_row.corruption_current if sineater_row is not None else 0
        shed = _largest_shed_arriving_within(
            sineater_sheet, resonance, shed, max(0, ceiling - carried)
        )

    holding = MireHolding.objects.filter(relationship=relationship, resonance=resonance).first()
    if shed <= 0:
        return MireTransfer(left_sinner=0, arrived=0, held=holding.amount if holding else 0)

    reduce_corruption(
        character_sheet=sinner_sheet,
        resonance=resonance,
        amount=shed,
        source=CorruptionRecoverySource.SINEATING,
        grant_resonance_back=False,
    )
    arrived = accrue_corruption(
        character_sheet=sineater_sheet,
        resonance=resonance,
        amount=shed,
        source=CorruptionSource.SINEATING_CARRIED,
    ).amount_applied

    holding, _ = MireHolding.objects.select_for_update().get_or_create(
        relationship=relationship, resonance=resonance
    )
    holding.amount += arrived
    holding.save(update_fields=["amount"])
    return MireTransfer(left_sinner=shed, arrived=arrived, held=holding.amount)


@transaction.atomic
def release_mire(*, holding: MireHolding, amount: int) -> int:
    """Lower the Sineater's corruption and this holding by up to ``amount``; return what left.

    The corruption comes off through ``reduce_corruption`` (source MIRE_SETTLED) without the
    resonance cleansing grants, and without shrinking holdings, since this lowers the one
    holding itself. Absolve, Condemn and Succumb all release through here.
    """
    released = min(amount, holding.amount)
    if released <= 0:
        return 0
    result = reduce_corruption(
        character_sheet=holding.relationship.source,
        resonance=holding.resonance,
        amount=released,
        source=CorruptionRecoverySource.MIRE_SETTLED,
        grant_resonance_back=False,
        shrink_holdings=False,
    )
    holding.amount -= result.amount_reduced
    holding.save(update_fields=["amount"])
    return result.amount_reduced
