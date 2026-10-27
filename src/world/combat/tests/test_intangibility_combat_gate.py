"""NPCs can target an intangible PC (#4742; was excluded in #1584 Task 8).

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
    """An incorporeal PC stays in the NPC target pool; resistance protects her."""

    def _make_intangibility_instance(self, character_objectdb):
        """Build an active intangibility ConditionInstance directly via factory (SQLite-safe)."""
        category = ConditionCategoryFactory(grants_intangibility=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(condition=template, target=character_objectdb)

    def test_enemy_npc_targets_an_intangible_pc(self):
        """With only an intangible PC in the fight, the ENEMY opponent still picks her."""
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        intangible_pc = CombatParticipantFactory(encounter=enc, status=ParticipantStatus.ACTIVE)
        enemy = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ENEMY)
        ThreatPoolEntryFactory(pool=enemy.threat_pool)

        self._make_intangibility_instance(intangible_pc.character_sheet.character)

        actions = select_npc_actions(enc)

        all_targets = [target for action in actions for target in action.targets.all()]
        self.assertIn(intangible_pc, all_targets, "Intangible PC is still an NPC target")
