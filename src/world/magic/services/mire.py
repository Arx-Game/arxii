"""The Mire: corruption a Sineater carries for their Sinners (#5177).

``MireHolding.amount`` says how much of a Sineater's corruption in a resonance came from
which Sinner. These two services are the only writers of that amount. When corruption falls
for any other reason, ``reduce_corruption`` keeps the holdings within it.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from django.db.models import OuterRef, Subquery, Sum

from world.character_sheets.models import CharacterSheet
from world.conditions.models import ConditionInstance
from world.magic.models.affinity import Resonance
from world.magic.models.aura import CharacterResonance
from world.magic.models.soul_tether import MireHolding
from world.magic.services.corruption import (
    _apply_sineater_corruption_resistance,
    accrue_corruption,
    reduce_corruption,
)
from world.magic.types.corruption import CorruptionRecoverySource, CorruptionSource
from world.magic.types.soul_tether import MireCarried, MireForSinner, MireTransfer
from world.relationships.models import CharacterRelationship
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


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


def own_corruptions(
    sinner_sheet: CharacterSheet, resonances: Iterable[Resonance]
) -> dict[int, int]:
    """For each of ``resonances`` (by id), the corruption a Sinner can shed in it.

    What she carries less what she holds in that resonance as a Sineater for someone else,
    which is not hers to pass on. Two queries however many resonances are asked about.
    """
    ids = [resonance.pk for resonance in resonances]
    carried = dict(
        CharacterResonance.objects.filter(
            character_sheet=sinner_sheet, resonance_id__in=ids
        ).values_list("resonance_id", "corruption_current")
    )
    held = dict(
        MireHolding.objects.filter(relationship__source=sinner_sheet, resonance_id__in=ids)
        .order_by()
        .values("resonance_id")
        .annotate(total=Sum("amount"))
        .values_list("resonance_id", "total")
    )
    return {pk: max(0, carried.get(pk, 0) - held.get(pk, 0)) for pk in ids}


def own_corruption(sinner_sheet: CharacterSheet, resonance: Resonance) -> int:
    """The corruption in ``resonance`` a Sinner can shed: what she carries less what she holds."""
    return own_corruptions(sinner_sheet, [resonance])[resonance.pk]


def corruption_that_can_move(
    *,
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    max_stage: int | None = None,
) -> tuple[int, int]:
    """What ``take_on_corruption`` would shed for ``amount``, without writing anything.

    Returns ``(carried, fits)``: ``carried`` is the most the Sinner could shed (``amount``
    capped at the corruption that is their own: what they carry less what they hold in this
    resonance as a Sineater for someone else, which they cannot pass on). ``fits`` is how much
    of that the Sineater can take on before their corruption in ``resonance`` reaches the
    stage after ``max_stage``. ``fits`` is below ``carried`` exactly when the cap cuts the
    move.
    """
    own = own_corruption(sinner_sheet, resonance)
    carried = min(amount, own)
    ceiling = corruption_ceiling(resonance, max_stage)
    if ceiling is None or carried <= 0:
        return carried, carried
    sineater_row = CharacterResonance.objects.filter(
        character_sheet=sineater_sheet, resonance=resonance
    ).first()
    held = sineater_row.corruption_current if sineater_row is not None else 0
    fits = _largest_shed_arriving_within(sineater_sheet, resonance, carried, max(0, ceiling - held))
    return carried, fits


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

    The Sinner never sheds more than their own corruption: what they hold for another Sinner
    as a Sineater stays with them, and its holding is untouched. ``max_stage`` caps the
    Sineater: their corruption in the resonance never reaches the threshold of the stage
    after it, and the Sinner sheds only what the Sineater can take. None means no cap.

    Raises:
        CharacterRelationship.DoesNotExist: the Sineater has no side toward this Sinner.
    """
    if amount <= 0:
        msg = f"amount must be > 0, got {amount}"
        raise ValueError(msg)
    relationship = CharacterRelationship.objects.get(source=sineater_sheet, target=sinner_sheet)
    _, shed = corruption_that_can_move(
        sineater_sheet=sineater_sheet,
        sinner_sheet=sinner_sheet,
        resonance=resonance,
        amount=amount,
        max_stage=max_stage,
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
        shrink_holdings=False,
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


@transaction.atomic
def add_to_largest_holding(sheet: CharacterSheet, resonance: Resonance, amount: int) -> bool:
    """Add ``amount`` to the Sineater's largest holding in ``resonance``; True when one grew.

    Corruption a Sineater adds to themselves by giving in to a Compulsion (#5177) is more of
    the Mire they carry, so the Sinner with the most held for them carries it. The corruption
    itself was already accrued; this only says whose it is, so holdings stay within it. Does
    nothing when the character holds nothing for anyone in this resonance.
    """
    if amount <= 0:
        return False
    holding = (
        MireHolding.objects.select_for_update()
        .filter(relationship__source=sheet, resonance=resonance, amount__gt=0)
        .order_by("-amount", "pk")
        .first()
    )
    if holding is None:
        return False
    holding.amount += amount
    holding.save(update_fields=["amount"])
    return True


def mire_carried_by(sineater_sheet: CharacterSheet) -> list[MireCarried]:
    """Every holding the Sineater carries, one row per Sinner and resonance, with its stage.

    One query for the holdings, with each Sinner's primary persona name read alongside, and one
    for the Sineater's corruption conditions, which say what stage their corruption in each
    resonance has reached and what to call it, however many Sinners they carry for (naming it
    reads the corruption config, a cached singleton). Largest holding first.
    A holding of nothing is not carried and is left out. The stage and label are the
    Sineater's own corruption in the resonance, not the holding's share of it.
    """
    from world.magic.services.impulses import corruption_display_name  # noqa: PLC0415

    primary_name = Persona.objects.filter(
        character_sheet=OuterRef("relationship__target"), persona_type=PersonaType.PRIMARY
    ).values("name")[:1]
    holdings = list(
        MireHolding.objects.filter(relationship__source=sineater_sheet, amount__gt=0)
        .select_related("resonance")
        .annotate(sinner_name=Subquery(primary_name))
        .order_by("-amount", "relationship__target_id", "resonance_id")
    )
    if not holdings:
        return []
    instances = {
        instance.condition.corruption_resonance_id: instance
        for instance in ConditionInstance.objects.filter(
            target_id=sineater_sheet.pk,
            condition__corruption_resonance__in={holding.resonance_id for holding in holdings},
            current_stage__isnull=False,
        ).select_related("condition", "current_stage")
    }
    carried = []
    for holding in holdings:
        instance = instances.get(holding.resonance_id)
        stage_order = instance.current_stage.stage_order if instance is not None else 0
        label = (
            corruption_display_name(instance, stage_order, holding.resonance)
            if instance is not None
            else holding.resonance.name
        )
        carried.append(
            MireCarried(
                sinner_sheet_id=holding.relationship.target_id,
                sinner_name=holding.sinner_name or "",
                resonance_name=holding.resonance.name,
                amount=holding.amount,
                stage_order=stage_order,
                label=label,
            )
        )
    return carried


def mire_for_sinner(sineater_sheet: CharacterSheet, sinner_sheet_id: int) -> MireForSinner | None:
    """What the Sineater carries for one Sinner, or None when they carry nothing for them."""
    rows = tuple(
        row for row in mire_carried_by(sineater_sheet) if row.sinner_sheet_id == sinner_sheet_id
    )
    if not rows:
        return None
    return MireForSinner(
        sinner_sheet_id=sinner_sheet_id,
        sinner_name=rows[0].sinner_name,
        rows=rows,
        total=sum(row.amount for row in rows),
    )
