"""Tests for the ship needs_repair battle-conclusion writeback (#1832 Task 7).

``apply_ship_battle_outcome`` is registered as a battle-conclusion hook in
``world.ships.apps.ready()``. Since that registration already happened at
Django startup, tests reset the registry to exactly this hook to avoid
duplicate firing or cross-test leakage from other suites' probe hooks.
"""

from __future__ import annotations

from django.test import TestCase

from world.battles.conclusion_hooks import (
    clear_battle_conclusion_hooks,
    register_battle_conclusion_hook,
)
from world.battles.constants import BattleOutcome, FortificationKind
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.models import Fortification
from world.battles.services import conclude_battle
from world.ships.battle_bridge import materialize_ship_as_battle_vehicle
from world.ships.battle_wiring import apply_ship_battle_outcome
from world.ships.factories import ShipDetailsFactory


class ApplyShipBattleOutcomeTests(TestCase):
    def setUp(self) -> None:
        clear_battle_conclusion_hooks()
        register_battle_conclusion_hook(apply_ship_battle_outcome)
        self.addCleanup(clear_battle_conclusion_hooks)

        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)

    def test_breached_hull_sets_needs_repair(self) -> None:
        ship = ShipDetailsFactory()
        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)
        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        fortification.breached = True
        fortification.save(update_fields=["breached"])

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        ship.refresh_from_db()
        self.assertTrue(ship.needs_repair)

    def test_unbreached_hull_leaves_needs_repair_false(self) -> None:
        ship = ShipDetailsFactory()
        materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        ship.refresh_from_db()
        self.assertFalse(ship.needs_repair)

    def test_apply_ship_battle_outcome_direct_call(self) -> None:
        ship = ShipDetailsFactory()
        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)
        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        fortification.breached = True
        fortification.save(update_fields=["breached"])

        apply_ship_battle_outcome(self.battle)

        ship.refresh_from_db()
        self.assertTrue(ship.needs_repair)
