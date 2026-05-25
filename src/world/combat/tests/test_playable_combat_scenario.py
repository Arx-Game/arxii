"""Smoke test for PlayableCombatScenarioFactory (Phase 10).

The factory composes a fully-playable combat encounter for integration
tests and (future) the `just demo-combat` recipe.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.constants import ClashStatus, EncounterStatus
from world.combat.factories import PlayableCombatScenarioFactory


class PlayableCombatScenarioSmokeTest(TestCase):
    """The scenario wires Scene + encounter + 2 PCs + NPC + active clash."""

    def test_default_scenario_has_expected_shape(self) -> None:
        scenario = PlayableCombatScenarioFactory.create()

        # Encounter in DECLARING.
        self.assertEqual(scenario.encounter.status, EncounterStatus.DECLARING)
        self.assertIsNotNone(scenario.encounter.scene)

        # 2 PC participants by default.
        self.assertEqual(len(scenario.participants), 2)

        # Each PC has vitals + anima + a clash-capable technique.
        for p in scenario.participants:
            self.assertGreater(p.character_sheet.vitals.health, 0)
            self.assertGreater(p.character_sheet.character.anima.current, 0)
            techs = list(p.character_sheet.character.techniques.all())
            self.assertGreater(len(techs), 0)
            self.assertTrue(any(t.clash_capable for t in techs))

        # NPC opponent ready to fight.
        self.assertGreater(scenario.opponent.health, 0)
        self.assertTrue(scenario.threat_entry.clash_capable)

        # Active clash on the opponent, initiated by PC 1.
        self.assertEqual(scenario.clash.status, ClashStatus.ACTIVE)
        self.assertEqual(scenario.clash.npc_opponent, scenario.opponent)
        self.assertEqual(scenario.clash.initiator, scenario.participants[0].character_sheet)

    def test_can_scale_pc_count(self) -> None:
        scenario = PlayableCombatScenarioFactory.create(num_pcs=4)
        self.assertEqual(len(scenario.participants), 4)
