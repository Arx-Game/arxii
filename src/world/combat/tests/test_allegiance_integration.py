"""Integration tests for allegiance-awareness across the combat sites (#1584).

Covers the victory/outcome path (an ALLY summon must not block victory) and NPC
target routing (an ENEMY opponent targets PCs; an ALLY summon does not target PCs).
The opponent-vs-opponent damage path (an ALLY summon dealing damage to an ENEMY
opponent via ``CombatOpponentAction.opponent_targets``) is exercised in
``test_opponent_vs_opponent.py`` (Task 7b).
"""

from django.test import TestCase

from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.services import _check_encounter_completion, select_npc_actions
from world.scenes.constants import RoundStatus


class AllegianceVictoryTests(TestCase):
    def test_ally_summon_does_not_block_victory(self):
        enc = CombatEncounterFactory()
        CombatParticipantFactory(encounter=enc)
        enemy = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ENEMY)
        CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)  # summon
        enemy.status = OpponentStatus.DEFEATED
        enemy.save(update_fields=["status"])
        # All ENEMY opponents down → completion even though an ALLY remains active.
        self.assertTrue(_check_encounter_completion(enc))


class AllegianceNpcTargetingTests(TestCase):
    def test_enemy_targets_pc_and_ally_summon_does_not(self):
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        pc = CombatParticipantFactory(encounter=enc)
        enemy = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ENEMY)
        ally = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)
        ThreatPoolEntryFactory(pool=enemy.threat_pool)
        ThreatPoolEntryFactory(pool=ally.threat_pool)

        actions = select_npc_actions(enc)

        enemy_actions = [a for a in actions if a.opponent_id == enemy.pk]
        ally_actions = [a for a in actions if a.opponent_id == ally.pk]

        # The ENEMY opponent routes its attack at the active PC participant.
        self.assertTrue(enemy_actions)
        self.assertIn(pc, list(enemy_actions[0].targets.all()))

        # The ALLY summon must NOT target the PC — its only hostiles are ENEMY
        # opponents, which the targets M2M cannot represent today, so it lands on
        # no PC (the honest under-supported state, not an attack on its own side).
        for action in ally_actions:
            self.assertNotIn(pc, list(action.targets.all()))
