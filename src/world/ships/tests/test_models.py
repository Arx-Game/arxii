"""Tests for ships models (#1832 Task 2)."""

from __future__ import annotations

from django.test import TestCase

from world.battles.factories import BattleVehicleFactory
from world.buildings.factories import BuildingFactory, BuildingKindFactory
from world.projects.constants import ProjectKind
from world.ships.constants import HANDLING_PER_LEVEL
from world.ships.factories import ShipDetailsFactory, ShipTypeFactory
from world.ships.models import ShipDeployment, ShipType


class ShipDetailsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ship_type = ShipTypeFactory(base_handling=10)
        cls.building = BuildingFactory(kind=BuildingKindFactory(is_maritime=True))
        cls.ship = ShipDetailsFactory(
            building=cls.building,
            ship_type=cls.ship_type,
            handling_level=2,
        )

    def test_effective_handling_applies_level_bonus(self) -> None:
        self.assertEqual(self.ship.effective_handling(), 10 + 2 * HANDLING_PER_LEVEL)

    def test_needs_repair_defaults_false(self) -> None:
        self.assertFalse(self.ship.needs_repair)

    def test_effective_hull_reads_building_fortification_level(self) -> None:
        self.assertEqual(self.ship.effective_hull(), self.building.fortification_level)

    def test_ship_deployment_can_be_created(self) -> None:
        vehicle = BattleVehicleFactory()
        deployment = ShipDeployment.objects.create(
            ship=self.ship,
            battle=vehicle.unit.battle,
            vehicle=vehicle,
        )

        self.assertEqual(deployment.ship, self.ship)
        self.assertEqual(deployment.vehicle, vehicle)

    def test_ship_type_ordering_is_by_name(self) -> None:
        ShipTypeFactory(name="Zeta Class")
        ShipTypeFactory(name="Alpha Class")

        names = list(ShipType.objects.values_list("name", flat=True))

        self.assertEqual(names, sorted(names))

    def test_ship_upgrade_project_kind_exists(self) -> None:
        self.assertEqual(ProjectKind.SHIP_UPGRADE.value, "SHIP_UPGRADE")
