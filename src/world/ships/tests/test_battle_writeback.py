"""Tests for the ship needs_repair battle-conclusion writeback (#1832 Task 7).

``apply_ship_battle_outcome`` is registered as a battle-conclusion hook in
``world.ships.apps.ready()``. Tests reset the registry to exactly this hook
(avoiding duplicate firing or cross-test leakage from other suites' probe
hooks), then snapshot and restore the pre-test contents on cleanup — clearing
to empty (rather than restoring) would permanently drop the production
registration for the rest of the test process.
"""

from __future__ import annotations

from django.test import TestCase

from world.battles import conclusion_hooks
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
        self._saved_hooks = list(conclusion_hooks._HOOKS)
        self.addCleanup(self._restore_hooks)

        clear_battle_conclusion_hooks()
        register_battle_conclusion_hook(apply_ship_battle_outcome)

        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)

    def _restore_hooks(self) -> None:
        conclusion_hooks._HOOKS[:] = self._saved_hooks

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
