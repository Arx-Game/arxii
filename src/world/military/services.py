"""Services for the military system.

Generic utilities for creating and managing persistent military units and
armies. These are service-layer functions, not gameplay logic — specific
military rules (food consumption, defense, mantles) are deferred to follow-up
issues.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.military.models import Army, ArmyMembership, MilitaryUnit


@transaction.atomic
def create_military_unit(  # noqa: PLR0913 - each param is a distinct unit attribute
    *,
    name: str,
    descriptor: str = "",
    owner_org=None,
    commander=None,
    quality: str = "trained",
    strength: int = 100,
    morale: int = 70,
    individual_count: int | None = None,
) -> MilitaryUnit:
    """Create a persistent MilitaryUnit.

    Args:
        name: Display name for the unit.
        descriptor: Optional flavor tag.
        owner_org: The Organization that owns this unit (None for transient).
        commander: Optional commanding CharacterSheet.
        quality: A UnitQuality value.
        strength: Starting strength value.
        morale: Starting morale value.
        individual_count: Optional swarm population data point.

    Returns:
        The newly created MilitaryUnit.
    """
    return MilitaryUnit.objects.create(
        name=name,
        descriptor=descriptor,
        owner_org=owner_org,
        commander=commander,
        quality=quality,
        strength=strength,
        morale=morale,
        individual_count=individual_count,
    )


@transaction.atomic
def form_army(
    *,
    name: str,
    commander=None,
    campaign_story=None,
    covenant=None,
    units: list[MilitaryUnit] | None = None,
) -> Army:
    """Create an Army and optionally add units to it.

    Args:
        name: Display name for the army.
        commander: Optional overall commander CharacterSheet.
        campaign_story: Optional campaign Story.
        covenant: Optional war Covenant organizing this force.
        units: Optional list of MilitaryUnits to add as initial members.

    Returns:
        The newly created Army.
    """
    army = Army.objects.create(
        name=name,
        commander=commander,
        campaign_story=campaign_story,
        covenant=covenant,
    )
    for unit in units or []:
        add_unit_to_army(army=army, military_unit=unit)
    return army


@transaction.atomic
def disband_army(*, army: Army) -> None:
    """Disband an army: mark all active memberships as left, set disbanded_at.

    The Army row is preserved for historical records. MilitaryUnits are not
    deleted — they persist and may join other armies.

    Args:
        army: The Army to disband.
    """
    now = timezone.now()
    ArmyMembership.objects.filter(army=army, left_at__isnull=True).update(left_at=now)
    army.disbanded_at = now
    army.save(update_fields=["disbanded_at"])


@transaction.atomic
def add_unit_to_army(*, army: Army, military_unit: MilitaryUnit) -> ArmyMembership:
    """Add a MilitaryUnit to an Army.

    A unit can be in multiple armies simultaneously. If the unit is already
    an active member of this army, returns the existing membership (idempotent).

    Args:
        army: The Army to add the unit to.
        military_unit: The MilitaryUnit to add.

    Returns:
        The ArmyMembership (created or existing).
    """
    membership, _created = ArmyMembership.objects.get_or_create(
        army=army,
        military_unit=military_unit,
        left_at__isnull=True,
    )
    return membership


@transaction.atomic
def remove_unit_from_army(*, army: Army, military_unit: MilitaryUnit) -> None:
    """Remove a MilitaryUnit from an Army (set left_at).

    No-op if the unit is not an active member of this army.

    Args:
        army: The Army to remove the unit from.
        military_unit: The MilitaryUnit to remove.
    """
    ArmyMembership.objects.filter(
        army=army,
        military_unit=military_unit,
        left_at__isnull=True,
    ).update(left_at=timezone.now())
