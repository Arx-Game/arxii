"""Tests for the battle-conclusion hook registry (#1832 Task 7).

Verifies that hooks registered via ``register_battle_conclusion_hook`` fire
when ``conclude_battle`` runs. ``world.ships.apps.ready()`` registers a hook
globally at Django startup, so tests snapshot the registry before clearing it
for isolation and restore the snapshot afterward — clearing to empty (rather
than restoring) would permanently drop the production hook for the rest of
the test process.
"""

from __future__ import annotations

from django.test import TestCase

from world.battles import conclusion_hooks
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
        self._saved_hooks = list(conclusion_hooks._HOOKS)
        self.addCleanup(self._restore_hooks)
        clear_battle_conclusion_hooks()
        self.calls = []

    def _restore_hooks(self) -> None:
        conclusion_hooks._HOOKS[:] = self._saved_hooks

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

    def test_restore_hooks_cleanup_repopulates_prior_contents(self) -> None:
        # Simulates a pre-existing production hook (e.g. apply_ship_battle_outcome
        # registered by world.ships.apps.ready()) that must survive this test's
        # clear/replace cycle instead of being permanently wiped.
        #
        # Uses a LOCAL snapshot on purpose: overwriting self._saved_hooks here
        # made the class-level cleanup restore [probe] instead of the real
        # registry, permanently dropping the production ship hook for every
        # test that ran after this module (surfaced as a ship-journey failure
        # when the CI shard rebalance first co-located battles and ships).
        simulated_prior = [self._probe]
        conclusion_hooks._HOOKS[:] = simulated_prior

        clear_battle_conclusion_hooks()
        register_battle_conclusion_hook(lambda _battle: None)
        self.assertNotEqual(conclusion_hooks._HOOKS, simulated_prior)

        conclusion_hooks._HOOKS[:] = simulated_prior  # the restore under test

        self.assertEqual(conclusion_hooks._HOOKS, [self._probe])
