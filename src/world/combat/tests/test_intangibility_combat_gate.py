"""Intangibility gate: select_npc_actions never targets an intangible PC (#1584 Task 8).

Uses direct ConditionInstance factory construction (not apply_condition) so these tests
run on the SQLite fast tier without hitting the PG-only DISTINCT ON path.
"""

from django.test import TestCase

from world.combat.constants import CombatAllegiance, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.services import select_npc_actions
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.scenes.constants import RoundStatus


class IntangibilityGateCombatTests(TestCase):
    """select_npc_actions excludes intangible participants from the NPC target pool."""

    def _make_intangibility_instance(self, character_objectdb):
        """Build an active intangibility ConditionInstance directly via factory (SQLite-safe)."""
        category = ConditionCategoryFactory(grants_intangibility=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(condition=template, target=character_objectdb)

    def test_enemy_npc_skips_intangible_pc_and_targets_tangible_pc(self):
        """An ENEMY opponent ignores an intangible PC and targets the remaining tangible PC."""
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        intangible_pc = CombatParticipantFactory(encounter=enc, status=ParticipantStatus.ACTIVE)
        tangible_pc = CombatParticipantFactory(encounter=enc, status=ParticipantStatus.ACTIVE)
        enemy = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ENEMY)
        ThreatPoolEntryFactory(pool=enemy.threat_pool)

        self._make_intangibility_instance(intangible_pc.character_sheet.character)

        actions = select_npc_actions(enc)

        self.assertTrue(actions, "Enemy with a valid target should produce at least one action")
        for action in actions:
            targeted = list(action.targets.all())
            self.assertNotIn(
                intangible_pc,
                targeted,
                "Intangible PC must never appear as an action target",
            )
        all_targets = [target for action in actions for target in action.targets.all()]
        self.assertIn(tangible_pc, all_targets, "Tangible PC must still be targeted")
