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
        """`ships` is a sub-package of the single collapsed `world` app (#2906).

        Pre-collapse, ``world.ships`` was its own installed app with label
        "ships". Post-collapse, every ``world.*`` sub-package (ships included)
        lives under the one installed app ``world.apps.ArxiiConfig`` (label
        "arxii") — there is no per-sub-package app config to look up anymore.
        `world.tests.test_aggregators` is the completeness guard that `ships`'s
        `models`/`admin` modules are actually wired into that single app; this
        test just confirms the sub-package itself is importable under it.
        """
        import world.ships

        config = apps.get_app_config("arxii")

        self.assertEqual(config.name, "world")
        self.assertTrue(world.ships.__name__.startswith(f"{config.name}."))

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
