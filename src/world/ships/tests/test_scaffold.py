"""Scaffold tests for the world/ships app (#1832 Task 1).

Confirms the app is registered and its constants/types/exceptions modules are
importable with the expected shapes, before any models exist.
"""

from __future__ import annotations

import dataclasses

from django.apps import apps
from django.test import SimpleTestCase


class ShipsAppScaffoldTests(SimpleTestCase):
    """The ships app is registered and its skeleton modules import cleanly."""

    def test_app_is_registered(self) -> None:
        config = apps.get_app_config("ships")

        self.assertEqual(config.name, "world.ships")

    def test_constants_import(self) -> None:
        from world.ships.constants import SHIP_KIND_NAME, ShipUpgradeStat

        self.assertEqual(SHIP_KIND_NAME, "Vessel")
        self.assertEqual(ShipUpgradeStat.HANDLING, "handling")
        self.assertEqual(ShipUpgradeStat.ARMAMENT, "armament")

    def test_ship_stat_bonus_defaults_and_frozen(self) -> None:
        from world.ships.types import ShipStatBonus

        bonus = ShipStatBonus(hull=1)

        self.assertEqual(bonus.hull, 1)
        self.assertEqual(bonus.handling, 0)
        self.assertEqual(bonus.armament, 0)

        with self.assertRaises(dataclasses.FrozenInstanceError):
            bonus.hull = 2  # type: ignore[misc]

    def test_exceptions_are_exception_subclasses(self) -> None:
        from world.ships.exceptions import (
            ShipConstructionError,
            ShipNeedsRepairError,
            ShipOwnershipError,
        )

        for exc_cls in (ShipNeedsRepairError, ShipConstructionError, ShipOwnershipError):
            self.assertTrue(issubclass(exc_cls, Exception))
            instance = exc_cls("boom")
            self.assertIn("boom", str(instance))
