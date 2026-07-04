"""Tests for ship upgrade/repair services + handlers (#1832 Task 4)."""

from __future__ import annotations

from django.test import TestCase

from world.projects.constants import ProjectKind
from world.projects.services import get_kind_handler
from world.scenes.factories import PersonaFactory
from world.ships.constants import ShipUpgradeStat
from world.ships.exceptions import ShipNeedsRepairError, ShipUpgradeError
from world.ships.factories import ShipDetailsFactory
from world.ships.models import ShipRepairDetails, ShipUpgradeDetails
from world.ships.services import (
    complete_ship_repair,
    complete_ship_upgrade,
    start_ship_hull_upgrade,
    start_ship_repair,
    start_ship_upgrade,
)


class StartShipUpgradeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.ship = ShipDetailsFactory(handling_level=1)

    def test_creates_project_and_upgrade_details(self) -> None:
        project = start_ship_upgrade(
            persona=self.persona,
            ship=self.ship,
            stat=ShipUpgradeStat.HANDLING,
            target_level=3,
        )

        self.assertEqual(project.kind, ProjectKind.SHIP_UPGRADE)
        self.assertEqual(project.owner_persona, self.persona)

        details = ShipUpgradeDetails.objects.get(project=project)
        self.assertEqual(details.ship, self.ship)
        self.assertEqual(details.stat, ShipUpgradeStat.HANDLING)
        self.assertEqual(details.target_level, 3)
        self.assertIsNone(details.applied_at)

    def test_raises_when_ship_needs_repair(self) -> None:
        self.ship.needs_repair = True
        self.ship.save(update_fields=["needs_repair"])

        with self.assertRaises(ShipNeedsRepairError) as ctx:
            start_ship_upgrade(
                persona=self.persona,
                ship=self.ship,
                stat=ShipUpgradeStat.HANDLING,
                target_level=3,
            )

        self.assertIn("repair", ctx.exception.user_message.lower())

    def test_raises_on_invalid_stat(self) -> None:
        with self.assertRaises(ShipUpgradeError):
            start_ship_upgrade(
                persona=self.persona,
                ship=self.ship,
                stat="not-a-real-stat",
                target_level=3,
            )

    def test_raises_when_target_not_greater_than_current(self) -> None:
        with self.assertRaises(ShipUpgradeError):
            start_ship_upgrade(
                persona=self.persona,
                ship=self.ship,
                stat=ShipUpgradeStat.HANDLING,
                target_level=1,
            )


class CompleteShipUpgradeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()

    def test_handler_registered_at_app_ready(self) -> None:
        handler = get_kind_handler(ProjectKind.SHIP_UPGRADE)

        self.assertIs(handler, complete_ship_upgrade)

    def test_applies_target_level(self) -> None:
        ship = ShipDetailsFactory(handling_level=1)
        project = start_ship_upgrade(
            persona=self.persona,
            ship=ship,
            stat=ShipUpgradeStat.HANDLING,
            target_level=3,
        )

        complete_ship_upgrade(project)
        ship.refresh_from_db()

        self.assertEqual(ship.handling_level, 3)
        details = ShipUpgradeDetails.objects.get(project=project)
        self.assertIsNotNone(details.applied_at)

    def test_monotonic_max_lower_target_after_higher_does_not_regress(self) -> None:
        ship = ShipDetailsFactory(handling_level=0)
        high_project = start_ship_upgrade(
            persona=self.persona,
            ship=ship,
            stat=ShipUpgradeStat.HANDLING,
            target_level=3,
        )
        low_project = start_ship_upgrade(
            persona=self.persona,
            ship=ship,
            stat=ShipUpgradeStat.HANDLING,
            target_level=2,
        )

        complete_ship_upgrade(high_project)
        complete_ship_upgrade(low_project)
        ship.refresh_from_db()

        self.assertEqual(ship.handling_level, 3)

    def test_completion_is_idempotent(self) -> None:
        ship = ShipDetailsFactory(armament_level=0)
        project = start_ship_upgrade(
            persona=self.persona,
            ship=ship,
            stat=ShipUpgradeStat.ARMAMENT,
            target_level=2,
        )

        complete_ship_upgrade(project)
        complete_ship_upgrade(project)
        ship.refresh_from_db()

        self.assertEqual(ship.armament_level, 2)


class StartShipHullUpgradeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()

    def test_delegates_to_fortification_upgrade(self) -> None:
        ship = ShipDetailsFactory()
        current_level = ship.building.fortification_level

        project = start_ship_hull_upgrade(
            persona=self.persona, ship=ship, target_level=current_level + 1
        )

        self.assertEqual(project.kind, ProjectKind.FORTIFICATION_UPGRADE)

    def test_raises_when_ship_needs_repair(self) -> None:
        ship = ShipDetailsFactory(needs_repair=True)

        with self.assertRaises(ShipNeedsRepairError) as ctx:
            start_ship_hull_upgrade(
                persona=self.persona,
                ship=ship,
                target_level=ship.building.fortification_level + 1,
            )

        self.assertIn("repair", ctx.exception.user_message.lower())


class ShipRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()

    def test_handler_registered_at_app_ready(self) -> None:
        handler = get_kind_handler(ProjectKind.SHIP_REPAIR)

        self.assertIs(handler, complete_ship_repair)

    def test_creates_project_and_repair_details(self) -> None:
        ship = ShipDetailsFactory(needs_repair=True)

        project = start_ship_repair(persona=self.persona, ship=ship)

        self.assertEqual(project.kind, ProjectKind.SHIP_REPAIR)
        details = ShipRepairDetails.objects.get(project=project)
        self.assertEqual(details.ship, ship)
        self.assertIsNone(details.applied_at)

    def test_completion_clears_needs_repair(self) -> None:
        ship = ShipDetailsFactory(needs_repair=True)
        project = start_ship_repair(persona=self.persona, ship=ship)

        complete_ship_repair(project)
        ship.refresh_from_db()

        self.assertFalse(ship.needs_repair)

    def test_completion_is_idempotent(self) -> None:
        ship = ShipDetailsFactory(needs_repair=True)
        project = start_ship_repair(persona=self.persona, ship=ship)

        complete_ship_repair(project)
        complete_ship_repair(project)
        ship.refresh_from_db()

        self.assertFalse(ship.needs_repair)
        self.assertEqual(ShipRepairDetails.objects.filter(project=project).count(), 1)
