"""E2E tests for NPC allegiance-aware targeting (#1590)."""

from django.test import TestCase

from world.combat.constants import TargetingMode, TargetSelection
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import select_npc_actions
from world.conditions.charm_content import ensure_charm_content
from world.conditions.constants import CALM_CONDITION_NAME, CHARM_CONDITION_NAME
from world.conditions.models import ConditionTemplate
from world.conditions.services import bulk_apply_conditions
from world.conditions.types import BulkConditionApplication
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class NpcAllegianceTargetingTest(TestCase):
    """NPC target selection respects derived allegiance (charm/calm)."""

    def setUp(self):
        super().setUp()
        ensure_charm_content()
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=self.pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
        )
        self.pc_a = self._make_active_participant()
        self.pc_b = self._make_active_participant()
        self.enemy_opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=self.pool)

    def _make_active_participant(self):
        participant = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=participant.character_sheet,
            health=100,
            max_health=100,
        )
        return participant

    def _apply_charm(self, opponent, source_participant):
        template = ConditionTemplate.objects.get(name=CHARM_CONDITION_NAME)
        bulk_apply_conditions(
            [BulkConditionApplication(target=opponent.objectdb, template=template)],
            source_character=source_participant.character_sheet.character,
        )

    def _apply_calm(self, opponent):
        template = ConditionTemplate.objects.get(name=CALM_CONDITION_NAME)
        bulk_apply_conditions(
            [BulkConditionApplication(target=opponent.objectdb, template=template)],
        )

    def _targeted_character_ids(self, actions):
        return {t.character_sheet_id for a in actions for t in a.targets.all()}

    def test_uncharmed_npc_targets_normally(self):
        actions = select_npc_actions(self.encounter)
        self.assertTrue(any(a.opponent_id == self.enemy_opponent.pk for a in actions))

    def test_charmed_npc_does_not_target_charmers_party(self):
        self._apply_charm(self.enemy_opponent, self.pc_a)
        actions = select_npc_actions(self.encounter)
        targeted = self._targeted_character_ids(actions)
        self.assertNotIn(self.pc_a.character_sheet_id, targeted)
        # The charmed NPC still acts; it just cannot target the charmer.
        self.assertTrue(any(a.opponent_id == self.enemy_opponent.pk for a in actions))

    def test_calmed_npc_takes_no_action(self):
        self._apply_calm(self.enemy_opponent)
        actions = select_npc_actions(self.encounter)
        self.assertEqual(
            [a for a in actions if a.opponent_id == self.enemy_opponent.pk],
            [],
        )
