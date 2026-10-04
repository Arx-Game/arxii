"""Standoff state: opening, settling, breaking into a fight."""

from django.test import TestCase

from world.combat.constants import OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.combat.services import begin_declaration_phase
from world.scenes.constants import RoundStatus
from world.standoffs.constants import StandoffGroupState
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    is_in_standoff,
    open_standoff,
    settle_empty_groups,
)


class StandoffStateTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=self.encounter)
        self.bandit = CreatureTemplateFactory()
        self.hound = CreatureTemplateFactory()
        self.bandits = [
            CombatOpponentFactory(encounter=self.encounter, creature_template=self.bandit)
            for _ in range(4)
        ]
        self.hound_opp = CombatOpponentFactory(
            encounter=self.encounter, creature_template=self.hound
        )
        self.plain = CombatOpponentFactory(encounter=self.encounter)

    def test_open_makes_one_group_per_template(self) -> None:
        groups = open_standoff(self.encounter)
        self.assertEqual(len(groups), 2)
        self.assertEqual({g.creature_template_id for g in groups}, {self.bandit.pk, self.hound.pk})
        self.assertTrue(all(g.state == StandoffGroupState.OPEN for g in groups))
        self.assertTrue(is_in_standoff(self.encounter))
        self.assertEqual(len(active_members(groups[0])) + len(active_members(groups[1])), 5)

    def test_open_with_no_templates_makes_no_groups(self) -> None:
        encounter = CombatEncounterFactory()
        CombatOpponentFactory(encounter=encounter)
        self.assertEqual(open_standoff(encounter), [])
        self.assertFalse(is_in_standoff(encounter))

    def test_end_standoff_begins_round_one(self) -> None:
        open_standoff(self.encounter)
        end_standoff_into_fight(self.encounter, initiated_by_pc_side=False)
        self.encounter.refresh_from_db()
        self.assertFalse(is_in_standoff(self.encounter))
        self.assertEqual(self.encounter.round_number, 1)
        self.assertEqual(self.encounter.status, RoundStatus.DECLARING)
        self.assertIs(self.encounter.initiated_by_pc_side, False)
        states = {g.state for g in self.encounter.standoff_groups.all()}
        self.assertEqual(states, {StandoffGroupState.FIGHTING})

    def test_begin_declaration_refused_during_standoff(self) -> None:
        open_standoff(self.encounter)
        with self.assertRaisesMessage(ValueError, "The standoff has not broken yet."):
            begin_declaration_phase(self.encounter)

    def test_fled_group_is_settled(self) -> None:
        open_standoff(self.encounter)
        self.hound_opp.status = OpponentStatus.FLED
        self.hound_opp.save(update_fields=["status"])
        settle_empty_groups(self.encounter)
        hound_group = self.encounter.standoff_groups.get(creature_template=self.hound)
        bandit_group = self.encounter.standoff_groups.get(creature_template=self.bandit)
        self.assertEqual(hound_group.state, StandoffGroupState.SETTLED)
        self.assertEqual(bandit_group.state, StandoffGroupState.OPEN)
        self.assertEqual(active_members(hound_group), [])
