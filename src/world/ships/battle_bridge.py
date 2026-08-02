"""Combat bridge: snapshot a persistent ship into an ephemeral BattleVehicle.

``materialize_ship_as_battle_vehicle`` is the one-way translation from the
persistent ``ShipDetails`` (upgrades/repair state, living on a ``Building``)
into the battle system's ``BattleVehicle`` (a paired ``BattleUnit`` +
``BattlePlace`` + hull ``Fortification``, per #1714/#1713). It is called once
per ship per battle deployment; the resulting ``ShipDeployment`` row is the
durable link back to the persistent ship (#1832 Task 2).
"""

from __future__ import annotations

from django.db import transaction

from world.battles.constants import (
    BASE_INTEGRITY,
    FORTIFICATION_LEVEL_INTEGRITY_BONUS,
    FortificationKind,
    VehicleKind,
)
from world.battles.models import (
    Battle,
    BattleSide,
    BattleVehicle,
    Fortification,
)
from world.battles.services import create_battle_vehicle
from world.conditions.models import CapabilityType
from world.military.models import MilitaryUnitCapability
from world.ships.constants import DAMAGED_HULL_DISCOUNT, SPEED_CAPABILITY_NAME
from world.ships.models import ShipDeployment, ShipDetails
from world.ships.sanctum_bonus import ship_sanctum_bonus, ship_sanctum_capability_grants


@transaction.atomic
def materialize_ship_as_battle_vehicle(
    *,
    ship: ShipDetails,
    battle: Battle,
    side: BattleSide,
    place_name: str | None = None,
) -> BattleVehicle:
    """Snapshot ``ship``'s persistent stats into a new in-battle ``BattleVehicle``.

    Creates the vehicle (unit + place + hull Fortification) via
    ``create_battle_vehicle``, links it back to ``ship`` via a
    ``ShipDeployment``, then overwrites the hull integrity ceiling and grants
    speed/strength/sanctum capabilities from the ship's persistent + sanctum
    stats.

    Both sanctum contributions — the stat bonus and the capabilities — are resolved
    in ``world/ships/sanctum_bonus.py`` off the authored ``ThreadPullEffect`` catalog.
    This function only writes what it is handed; it invents no capability and no
    magnitude (#2736).

    Args:
        ship: The persistent ship being deployed.
        battle: The Battle the vehicle joins.
        side: The BattleSide crewing the vehicle.
        place_name: Optional display name; defaults to the ship's area name.

    Returns:
        The newly created BattleVehicle, fully stat-snapshotted.
    """
    vehicle = create_battle_vehicle(
        battle=battle,
        side=side,
        place_name=place_name or ship.building.area.name,
        vehicle_kind=VehicleKind.SHIP,
        is_structural=True,
    )
    ShipDeployment.objects.create(ship=ship, battle=battle, vehicle=vehicle)

    bonus = ship_sanctum_bonus(ship)

    # Hull: overwrite the ad-hoc Fortification create_battle_vehicle made
    # (building=None there) with the ship's actual persistent hull level.
    level = ship.building.fortification_level + bonus.hull
    integrity = BASE_INTEGRITY[FortificationKind.HULL] + level * FORTIFICATION_LEVEL_INTEGRITY_BONUS
    if ship.needs_repair:
        discount = DAMAGED_HULL_DISCOUNT * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        integrity = max(1, integrity - discount)
    fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
    fortification.integrity = integrity
    fortification.max_integrity = integrity
    fortification.save(update_fields=["integrity", "max_integrity"])

    # Handling -> speed, read by REPOSITION (world/battles/resolution.py:726).
    speed, _ = CapabilityType.objects.get_or_create(name=SPEED_CAPABILITY_NAME)
    MilitaryUnitCapability.objects.update_or_create(
        unit=vehicle.unit.military_unit,
        capability=speed,
        defaults={"value": ship.effective_handling() + bonus.handling},
    )

    # Armament -> strength.
    vehicle.unit.military_unit.strength = ship.effective_armament() + bonus.armament
    vehicle.unit.military_unit.save(update_fields=["strength"])

    # Sanctum threads confer whatever the authored catalog says they confer (#2736).
    # This loop deliberately mints nothing: it writes only capabilities that already
    # exist as authored content. The pre-#2736 version get_or_create'd a
    # `sanctum_<resonance>` CapabilityType per resonance, which grew the exported
    # content corpus by a row per resonance any player ever levelled — the #2724
    # defect class — and named a *provenance* where every other capability names a
    # *capacity*. See ADR-0188.
    for grant in ship_sanctum_capability_grants(ship):
        MilitaryUnitCapability.objects.update_or_create(
            unit=vehicle.unit.military_unit,
            capability=grant.capability,
            defaults={"value": grant.value},
        )

    return vehicle
