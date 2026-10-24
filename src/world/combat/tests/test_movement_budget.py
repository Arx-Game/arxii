"""Unit tests for the PC hop budget helpers (#4607).

The prerequisite and action behaviour is proven by the wall-crossing journeys.
"""

from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services.movement_budget import (
    active_combat_participant,
    hops_for,
    hops_left,
    spend_combat_hop,
)
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import CapabilityTypeFactory
from world.scenes.constants import RoundStatus

_VALUE_PATH = "world.conditions.services.get_effective_capability_value"


class HopsForTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        CapabilityTypeFactory(name=FoundationalCapability.MOVEMENT)
        cls.sheet = CharacterSheetFactory()

    def _hops(self, value: int) -> int:
        with patch(_VALUE_PATH, return_value=value):
            return hops_for(self.sheet)

    def test_mortal_gets_one_hop(self) -> None:
        self.assertEqual(self._hops(5), 1)

    def test_stronger_mover_gets_more(self) -> None:
        self.assertEqual(self._hops(12), 2)

    def test_hops_are_capped(self) -> None:
        self.assertEqual(self._hops(30), 5)

    def test_slow_but_moving_still_gets_one(self) -> None:
        self.assertEqual(self._hops(1), 1)

    def test_rooted_gets_none(self) -> None:
        self.assertEqual(self._hops(0), 0)


class ActiveCombatParticipantTests(TestCase):
    def setUp(self) -> None:
        CapabilityTypeFactory(name=FoundationalCapability.MOVEMENT)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.character.location = self.encounter.room
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def test_found_in_the_encounter_room(self) -> None:
        self.assertEqual(active_combat_participant(self.character), self.participant)

    def test_resolving_and_between_rounds_still_count(self) -> None:
        for status in (RoundStatus.RESOLVING, RoundStatus.BETWEEN_ROUNDS):
            self.encounter.status = status
            self.encounter.save(update_fields=["status"])
            self.assertEqual(active_combat_participant(self.character), self.participant)

    def test_other_room_is_none(self) -> None:
        elsewhere = create_object("typeclasses.rooms.Room", key="Elsewhere", nohome=True)
        self.character.location = elsewhere
        self.assertIsNone(active_combat_participant(self.character))

    def test_completed_encounter_is_none(self) -> None:
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        self.assertIsNone(active_combat_participant(self.character))

    def test_removed_participant_is_none(self) -> None:
        self.participant.status = ParticipantStatus.REMOVED
        self.participant.save(update_fields=["status"])
        self.assertIsNone(active_combat_participant(self.character))


class SpendHopTests(TestCase):
    def test_spending_reduces_hops_left(self) -> None:
        CapabilityTypeFactory(name=FoundationalCapability.MOVEMENT)
        participant = CombatParticipantFactory()
        with patch(_VALUE_PATH, return_value=10):
            self.assertEqual(hops_left(participant), 2)
            spend_combat_hop(participant)
            self.assertEqual(hops_left(participant), 1)
            spend_combat_hop(participant)
            spend_combat_hop(participant)
            self.assertEqual(hops_left(participant), 0)
