"""Tests for active_conditions on Participant + Opponent serializers (#553)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import OpponentSerializer, ParticipantSerializer
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)


class ParticipantActiveConditionsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.encounter.participants_cached = [self.participant]
        self.character = self.sheet.character

    def _staff_request(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        staff = AccountFactory()
        staff.is_staff = True
        staff.save()
        request.user = staff
        return request

    def _outsider_request(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = AccountFactory()
        return request

    def test_active_conditions_serialized_shape(self) -> None:
        public = ConditionTemplateFactory(
            name="PublicCondition",
            is_visible_to_others=True,
            display_priority=5,
            icon="skull",
            color_hex="#ff0000",
        )
        ConditionInstanceFactory(target=self.character, condition=public)
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data

        conditions = data["active_conditions"]
        self.assertEqual(len(conditions), 1)
        entry = conditions[0]
        for key in ("id", "name", "icon", "color_hex", "display_priority"):
            self.assertIn(key, entry)
        self.assertEqual(entry["name"], "PublicCondition")
        self.assertEqual(entry["display_priority"], 5)

    def test_hidden_condition_visible_to_staff(self) -> None:
        hidden = ConditionTemplateFactory(name="HiddenCondition", is_visible_to_others=False)
        ConditionInstanceFactory(target=self.character, condition=hidden)
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data
        names = [c["name"] for c in data["active_conditions"]]
        self.assertIn("HiddenCondition", names)

    def test_hidden_condition_excluded_for_outsider(self) -> None:
        public = ConditionTemplateFactory(name="PublicCondition", is_visible_to_others=True)
        hidden = ConditionTemplateFactory(name="HiddenCondition", is_visible_to_others=False)
        ConditionInstanceFactory(target=self.character, condition=public)
        ConditionInstanceFactory(target=self.character, condition=hidden)
        request = self._outsider_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data
        names = [c["name"] for c in data["active_conditions"]]
        self.assertIn("PublicCondition", names)
        self.assertNotIn("HiddenCondition", names)

    def test_ordered_by_display_priority(self) -> None:
        low = ConditionTemplateFactory(
            name="LowPriority", is_visible_to_others=True, display_priority=1
        )
        high = ConditionTemplateFactory(
            name="HighPriority", is_visible_to_others=True, display_priority=9
        )
        ConditionInstanceFactory(target=self.character, condition=low)
        ConditionInstanceFactory(target=self.character, condition=high)
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data
        names = [c["name"] for c in data["active_conditions"]]
        self.assertEqual(names, ["HighPriority", "LowPriority"])

    def test_empty_when_no_conditions(self) -> None:
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data
        self.assertEqual(data["active_conditions"], [])


class OpponentActiveConditionsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.target = self.opponent.objectdb

    def _staff_request(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        staff = AccountFactory()
        staff.is_staff = True
        staff.save()
        request.user = staff
        return request

    def _outsider_request(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = AccountFactory()
        return request

    def test_opponent_public_condition_serialized(self) -> None:
        public = ConditionTemplateFactory(
            name="OppPublic", is_visible_to_others=True, display_priority=3
        )
        ConditionInstanceFactory(target=self.target, condition=public)
        request = self._outsider_request()
        data = OpponentSerializer(self.opponent, context={"request": request}).data
        conditions = data["active_conditions"]
        self.assertEqual(len(conditions), 1)
        for key in ("id", "name", "icon", "color_hex", "display_priority"):
            self.assertIn(key, conditions[0])
        self.assertEqual(conditions[0]["name"], "OppPublic")

    def test_opponent_hidden_condition_excluded_for_outsider(self) -> None:
        hidden = ConditionTemplateFactory(name="OppHidden", is_visible_to_others=False)
        ConditionInstanceFactory(target=self.target, condition=hidden)
        request = self._outsider_request()
        data = OpponentSerializer(self.opponent, context={"request": request}).data
        self.assertEqual(data["active_conditions"], [])

    def test_opponent_hidden_condition_visible_to_staff(self) -> None:
        hidden = ConditionTemplateFactory(name="OppHidden", is_visible_to_others=False)
        ConditionInstanceFactory(target=self.target, condition=hidden)
        request = self._staff_request()
        data = OpponentSerializer(self.opponent, context={"request": request}).data
        names = [c["name"] for c in data["active_conditions"]]
        self.assertIn("OppHidden", names)

    def test_opponent_empty_when_no_conditions(self) -> None:
        request = self._staff_request()
        data = OpponentSerializer(self.opponent, context={"request": request}).data
        self.assertEqual(data["active_conditions"], [])
