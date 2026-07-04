"""Tests for the battle-conclusion hook registry (#1832 Task 7).

Verifies that hooks registered via ``register_battle_conclusion_hook`` fire
when ``conclude_battle`` runs. ``world.ships.apps.ready()`` registers a hook
globally at Django startup, so tests clear and restore the registry to avoid
cross-test leakage.
"""

from __future__ import annotations

from django.test import TestCase

from world.battles.conclusion_hooks import (
    clear_battle_conclusion_hooks,
    register_battle_conclusion_hook,
    run_battle_conclusion_hooks,
)
from world.battles.constants import BattleOutcome
from world.battles.factories import BattleFactory
from world.battles.services import conclude_battle


class BattleConclusionHookRegistryTests(TestCase):
    def setUp(self) -> None:
        clear_battle_conclusion_hooks()
        self.calls = []
        self.addCleanup(clear_battle_conclusion_hooks)

    def _probe(self, battle) -> None:
        self.calls.append(battle)

    def test_run_battle_conclusion_hooks_calls_registered_hook(self) -> None:
        register_battle_conclusion_hook(self._probe)
        battle = BattleFactory()

        run_battle_conclusion_hooks(battle)

        self.assertEqual(self.calls, [battle])

    def test_conclude_battle_fires_registered_hook(self) -> None:
        register_battle_conclusion_hook(self._probe)
        battle = BattleFactory()

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        self.assertEqual(self.calls, [battle])

    def test_clear_battle_conclusion_hooks_empties_registry(self) -> None:
        register_battle_conclusion_hook(self._probe)
        clear_battle_conclusion_hooks()
        battle = BattleFactory()

        run_battle_conclusion_hooks(battle)

        self.assertEqual(self.calls, [])
