"""Turn order modifier conditions shift round order and the initiative chips (#4572)."""

from django.test import TestCase

from world.combat.constants import ENTITY_TYPE_NPC, ENTITY_TYPE_PC
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant
from world.combat.serializers import EncounterDetailSerializer
from world.combat.services import get_resolution_order
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.covenants.factories import CovenantRoleFactory
from world.vitals.models import CharacterVitals


class TurnOrderConditionTests(TestCase):
    """get_resolution_order ranks by base speed minus the bearer's turn order modifier."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()
        cls.haste = ConditionTemplateFactory(
            name="Haste 4572 order", affects_turn_order=True, turn_order_modifier=5
        )
        cls.slow = ConditionTemplateFactory(
            name="Slow 4572 order", affects_turn_order=True, turn_order_modifier=-5
        )

    def _pc(self, speed_rank):
        pc = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=speed_rank),
        )
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet, health=100, max_health=100
        )
        return pc

    def _condition(self, bearer, template):
        ConditionInstanceFactory(target=bearer, condition=template)

    def test_haste_outweighing_the_rank_gap_acts_first(self):
        fast = self._pc(speed_rank=2)
        slow_role = self._pc(speed_rank=6)
        self._condition(slow_role.character_sheet.character, self.haste)

        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [(ENTITY_TYPE_PC, slow_role), (ENTITY_TYPE_PC, fast)])

    def test_haste_smaller_than_the_rank_gap_keeps_order(self):
        fast = self._pc(speed_rank=2)
        slow_role = self._pc(speed_rank=10)
        self._condition(slow_role.character_sheet.character, self.haste)

        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [(ENTITY_TYPE_PC, fast), (ENTITY_TYPE_PC, slow_role)])

    def test_negative_modifier_moves_a_pc_later(self):
        hindered = self._pc(speed_rank=2)
        steady = self._pc(speed_rank=4)
        self._condition(hindered.character_sheet.character, self.slow)

        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [(ENTITY_TYPE_PC, steady), (ENTITY_TYPE_PC, hindered)])

    def test_npc_with_a_condition_moves(self):
        pc = self._pc(speed_rank=10)
        npc = CombatOpponentFactory(encounter=self.encounter)
        self.assertEqual(get_resolution_order(self.encounter)[0], (ENTITY_TYPE_PC, pc))

        self._condition(npc.objectdb, self.haste)
        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [(ENTITY_TYPE_NPC, npc), (ENTITY_TYPE_PC, pc)])

    def test_slowed_npc_acts_after_a_no_role_pc(self):
        pc = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet, health=100, max_health=100
        )
        npc = CombatOpponentFactory(encounter=self.encounter)
        self._condition(npc.objectdb, self.slow)

        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [(ENTITY_TYPE_PC, pc), (ENTITY_TYPE_NPC, npc)])

    def test_initiative_chips_match_the_resolution_order(self):
        fast = self._pc(speed_rank=2)
        hasted = self._pc(speed_rank=6)
        hindered = self._pc(speed_rank=3)
        self._condition(hasted.character_sheet.character, self.haste)
        self._condition(hindered.character_sheet.character, self.slow)

        self.encounter.participants_cached = list(
            CombatParticipant.objects.filter(encounter=self.encounter).select_related(
                "covenant_role", "character_sheet__character"
            )
        )
        chips = EncounterDetailSerializer().get_resolution_order(self.encounter)

        real_pc_order = [
            entity.pk
            for entity_type, entity in get_resolution_order(self.encounter)
            if entity_type == ENTITY_TYPE_PC
        ]
        self.assertEqual(chips, [hasted.pk, fast.pk, hindered.pk])
        self.assertEqual(chips, real_pc_order)
