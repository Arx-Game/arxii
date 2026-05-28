"""Unit tests for next_available_name auto-suffix helper."""

from django.test import TestCase

from world.missions.factories import MissionTemplateFactory
from world.missions.models import MissionTemplate
from world.missions.services.naming import next_available_name


class NextAvailableNameTests(TestCase):
    def test_returns_base_name_when_no_collision(self) -> None:
        result = next_available_name("Heist the Castle", MissionTemplate.objects.all())
        self.assertEqual(result, "Heist the Castle")

    def test_suffixes_with_2_when_base_taken(self) -> None:
        MissionTemplateFactory(name="Heist the Castle")
        result = next_available_name("Heist the Castle", MissionTemplate.objects.all())
        self.assertEqual(result, "Heist the Castle 2")

    def test_suffixes_with_3_when_base_and_2_taken(self) -> None:
        MissionTemplateFactory(name="Heist the Castle")
        MissionTemplateFactory(name="Heist the Castle 2")
        result = next_available_name("Heist the Castle", MissionTemplate.objects.all())
        self.assertEqual(result, "Heist the Castle 3")

    def test_truncates_base_when_suffix_would_overflow(self) -> None:
        # max_length=200; suffix " 2" is 2 chars; base must fit in 198.
        long_base = "X" * 200
        MissionTemplateFactory(name=long_base)
        result = next_available_name(long_base, MissionTemplate.objects.all(), max_length=200)
        self.assertEqual(len(result), 200)
        self.assertTrue(result.endswith(" 2"))
        self.assertEqual(result, ("X" * 198) + " 2")

    def test_respects_custom_max_length(self) -> None:
        MissionTemplateFactory(name="abcdef")
        result = next_available_name("abcdef", MissionTemplate.objects.all(), max_length=8)
        # "abcdef" + " 2" = 8 chars, fits exactly
        self.assertEqual(result, "abcdef 2")

    def test_truncates_when_custom_max_length_smaller_than_base(self) -> None:
        MissionTemplateFactory(name="hello")
        # max_length=6, suffix " 2" needs 2 chars, base fits in 4
        result = next_available_name("hello", MissionTemplate.objects.all(), max_length=6)
        self.assertEqual(result, "hell 2")
