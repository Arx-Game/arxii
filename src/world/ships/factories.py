"""FactoryBoy factories for the ships system (#1832)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.buildings.factories import BuildingFactory, BuildingKindFactory
from world.ships.models import ShipDetails, ShipType


class ShipTypeFactory(DjangoModelFactory):
    class Meta:
        model = ShipType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"ship-type-{n}")
    description = ""
    base_hull = 10
    base_handling = 10
    base_armament = 10
    base_crew_capacity = 10
    base_cargo_capacity = 10


class ShipDetailsFactory(DjangoModelFactory):
    class Meta:
        model = ShipDetails

    building = factory.SubFactory(
        BuildingFactory,
        kind=factory.SubFactory(BuildingKindFactory, is_maritime=True),
    )
    ship_type = factory.SubFactory(ShipTypeFactory)
    handling_level = 0
    armament_level = 0
    crew_capacity = 10
    cargo_capacity = 10
    needs_repair = False


def ensure_ship_types() -> dict[str, ShipType]:
    """Get-or-create a small starter roster of ship types.

    Deterministic via ``ShipType.name`` uniqueness, so this doubles as test
    setup and as production seed data for the initial ship-type catalog.
    PLACEHOLDER numbers pending balance passes.
    """
    roster = {
        "Sloop": {
            "description": "A small, nimble single-masted vessel.",
            "base_hull": 8,
            "base_handling": 15,
            "base_armament": 5,
            "base_crew_capacity": 8,
            "base_cargo_capacity": 10,
        },
        "Brigantine": {
            "description": "A two-masted vessel balancing speed and cargo.",
            "base_hull": 15,
            "base_handling": 10,
            "base_armament": 12,
            "base_crew_capacity": 20,
            "base_cargo_capacity": 30,
        },
        "Galleon": {
            "description": "A large, heavily-armed cargo and war vessel.",
            "base_hull": 30,
            "base_handling": 5,
            "base_armament": 25,
            "base_crew_capacity": 60,
            "base_cargo_capacity": 100,
        },
    }

    ship_types: dict[str, ShipType] = {}
    for name, defaults in roster.items():
        ship_type, _ = ShipType.objects.get_or_create(name=name, defaults=defaults)
        ship_types[name] = ship_type
    return ship_types
