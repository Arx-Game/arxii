"""Tests for fatigue pools on ParticipantSerializer (#552)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import ParticipantSerializer
from world.fatigue.constants import (
    CAPACITY_STAT_MULTIPLIER,
    CAPACITY_WILLPOWER_MULTIPLIER,
    ActionCategory,
)
from world.fatigue.models import FatiguePool
from world.fatigue.tests import setup_stat as _setup_stat
from world.traits.models import TraitCategory


class ParticipantSerializerFatigueTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        FatiguePool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        # Make the encounter's participants_cached attribute available for the
        # vitals-permission check that walks it.
        self.encounter.participants_cached = [self.participant]

        # Give the sheet known endurance stats so capacities are deterministic.
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)  # display 3
        _setup_stat(char, "composure", 40, TraitCategory.SOCIAL)  # display 4
        _setup_stat(char, "stability", 50, TraitCategory.MENTAL)  # display 5
        _setup_stat(char, "willpower", 20, TraitCategory.META)  # display 2

        self.expected_capacity = {
            ActionCategory.PHYSICAL.value: (
                3 * CAPACITY_STAT_MULTIPLIER + 2 * CAPACITY_WILLPOWER_MULTIPLIER
            ),
            ActionCategory.SOCIAL.value: (
                4 * CAPACITY_STAT_MULTIPLIER + 2 * CAPACITY_WILLPOWER_MULTIPLIER
            ),
            ActionCategory.MENTAL.value: (
                5 * CAPACITY_STAT_MULTIPLIER + 2 * CAPACITY_WILLPOWER_MULTIPLIER
            ),
        }

    def _staff_request(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        staff = AccountFactory()
        staff.is_staff = True
        staff.save()
        request.user = staff
        return request

    def test_fatigue_field_reports_current_and_capacity(self) -> None:
        FatiguePool.objects.create(
            character_sheet=self.sheet,
            physical_current=4,
            social_current=7,
            mental_current=2,
        )
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data

        fatigue = data["fatigue"]
        self.assertEqual(
            fatigue["physical"],
            {"current": 4, "capacity": self.expected_capacity["physical"]},
        )
        self.assertEqual(
            fatigue["social"],
            {"current": 7, "capacity": self.expected_capacity["social"]},
        )
        self.assertEqual(
            fatigue["mental"],
            {"current": 2, "capacity": self.expected_capacity["mental"]},
        )

    def test_fatigue_field_defaults_to_zero_current_with_no_pool(self) -> None:
        # No FatiguePool row exists for this sheet -> current values default to 0,
        # while capacity is still derived from the character's stats.
        request = self._staff_request()
        data = ParticipantSerializer(self.participant, context={"request": request}).data

        fatigue = data["fatigue"]
        for category in ActionCategory:
            self.assertEqual(fatigue[category.value]["current"], 0)
            self.assertEqual(
                fatigue[category.value]["capacity"],
                self.expected_capacity[category.value],
            )

    def test_fatigue_field_hidden_from_outsiders(self) -> None:
        FatiguePool.objects.create(character_sheet=self.sheet, physical_current=4)
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = AccountFactory()

        data = ParticipantSerializer(self.participant, context={"request": request}).data
        self.assertIsNone(data["fatigue"])
