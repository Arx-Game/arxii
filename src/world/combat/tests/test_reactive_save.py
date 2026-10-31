"""Reactions cost more each time, and the healer's reactive save (#4810, slice 6 of #4759).

- Interpose fatigue rises with ``reactions_used``: base x (1 + step x reactions
  already made this round), step = ``MovementConfig.reaction_difficulty_step``.
- A covenant healer whose vow specialises in Mend and who knows a Mend technique
  softens a blow that would drop an ally, through the real damage path
  (``apply_damage_to_participant``). It is a reaction: her own declaration stays
  hers, and each save costs more anima than the last.

``dispatch_interpose`` (the guardian's own roll) is mocked out for the interpose
tests, as in ``test_standing_guard.py``: they isolate cost. Built in ``setUp``
(not ``setUpTestData``): the tests mutate participant, vitals and anima rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.combat.constants import (
    INTERPOSE_BASE_FATIGUE_COST,
    ActionCategory,
    CombatManeuver,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import _try_interpose, apply_damage_to_participant
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
)
from world.fatigue.constants import EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models.anima import CharacterAnima
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory

NARRATE_PATH = "world.scenes.interaction_services.narrate_privately"


def _payload(amount: int = 10) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(
        target=MagicMock(),
        amount=amount,
        damage_type=None,
        source=DamageSource(type="character", ref=None),
    )


class InterposeFatigueRisesTests(TestCase):
    """Each interpose in one round costs more fatigue than the one before."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.ward = CombatParticipantFactory(encounter=self.encounter)
        self.guardian = CombatParticipantFactory(encounter=self.encounter)
        CombatRoundActionFactory(
            participant=self.guardian,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ward,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            is_ready=True,
        )

    def _fatigue(self) -> int:
        pool = get_or_create_fatigue_pool(self.guardian.character_sheet)
        return pool.get_current(ActionCategory.PHYSICAL)

    @patch("world.combat.services.dispatch_interpose")
    def test_second_and_third_interpose_each_cost_more(self, dispatch) -> None:
        dispatch.return_value = MagicMock()
        costs = []
        for _ in range(3):
            before = self._fatigue()
            _try_interpose(self.ward, _payload(10))
            costs.append(self._fatigue() - before)

        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.reactions_used, 3)
        # MEDIUM effort is x1.0; reaction_difficulty_step defaults to 2: 3, 9, 15.
        self.assertEqual(costs[0], INTERPOSE_BASE_FATIGUE_COST)
        self.assertLess(costs[0], costs[1])
        self.assertLess(costs[1], costs[2])
        self.assertEqual(costs, [3, 9, 15])


class ReactiveSaveTests(TestCase):
    """A covenant healer softens a blow that would drop her ally, as a reaction."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        covenant = CovenantFactory()
        self.healer_role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=self.healer_role, function=TechniqueFunction.MEND
        )

        self.ward_vitals = CharacterVitalsFactory(health=30, max_health=100)
        self.ward = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.ward_vitals.character_sheet
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.ward.character_sheet, covenant=covenant, engaged=True
        )

        self.healer = CombatParticipantFactory(encounter=self.encounter)
        healer_sheet = self.healer.character_sheet
        CharacterCovenantRoleFactory(
            character_sheet=healer_sheet,
            covenant=covenant,
            covenant_role=self.healer_role,
            engaged=True,
        )
        mend = TechniqueFunctionTagFactory(function=TechniqueFunction.MEND)
        CharacterTechniqueFactory(character=healer_sheet, technique=mend.technique)
        CharacterAnimaFactory(character=healer_sheet, current=10, maximum=10)
        # Her own turn this round: the save must not touch it.
        self.healer_action = CombatRoundActionFactory(
            participant=self.healer,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            is_ready=True,
        )

    def _anima(self) -> int:
        return CharacterAnima.objects.get(character_id=self.healer.character_sheet_id).current

    def test_a_blow_that_would_drop_an_ally_is_softened_and_she_keeps_her_turn(self) -> None:
        with patch(NARRATE_PATH):
            result = apply_damage_to_participant(self.ward, 14)

        # 30 - 14 = 16 would drop her (knockout line 20). Softened to 9 (just above
        # the line; at most half the blow off), she stands at 21.
        self.assertEqual(result.damage_dealt, 9)
        self.assertEqual(result.health_after, 21)
        self.assertFalse(result.knockout_eligible)
        self.healer.refresh_from_db()
        self.assertEqual(self.healer.reactions_used, 1)
        self.assertEqual(self._anima(), 8)  # dodge_anima_cost default 2
        # The save is a reaction: her declared action for the round is unchanged.
        action = CombatRoundAction.objects.get(pk=self.healer_action.pk)
        self.assertEqual(action.participant_id, self.healer.pk)
        self.assertTrue(action.is_ready)
        self.assertEqual(CombatRoundAction.objects.filter(participant=self.healer).count(), 1)

    def test_a_later_save_in_the_round_costs_more_anima(self) -> None:
        self.healer.reactions_used = 1
        self.healer.save(update_fields=["reactions_used"])

        with patch(NARRATE_PATH):
            apply_damage_to_participant(self.ward, 14)

        self.assertEqual(self._anima(), 10 - 6)  # 2 x (1 + 2 x 1)

    def test_a_blow_that_would_not_drop_her_is_untouched(self) -> None:
        result = apply_damage_to_participant(self.ward, 5)

        self.assertEqual(result.damage_dealt, 5)
        self.assertEqual(self._anima(), 10)

    def test_no_save_without_a_vow_that_specialises_in_mend(self) -> None:
        self.healer_role.technique_specialties.all().delete()

        result = apply_damage_to_participant(self.ward, 14)

        self.assertEqual(result.damage_dealt, 14)
        self.assertEqual(self._anima(), 10)
