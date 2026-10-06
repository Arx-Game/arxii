"""Audere and Audere Majora add effective levels to every check (#4147)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.services import _compute_check_breakdown
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    AUDERE_MAJORA_CONDITION_NAME,
    audere_check_level_bonus,
)
from world.magic.factories import AudereMajoraThresholdFactory, AudereThresholdFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import ResultChart, Trait

CHARACTER_LEVEL = 3
PATH_LEVEL = "world.progression.services.skill_development.get_character_path_level"


class AudereCheckLevelBonusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet,
            character_class=CharacterClassFactory(),
            level=CHARACTER_LEVEL,
            is_primary=True,
        )
        cls.character = sheet.character
        cls.check_type = CheckTypeFactory(
            name="audere_level_bonus_check",
            category=CheckCategoryFactory(name="audere_level_bonus_check"),
        )
        cls.audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        cls.majora_template = ConditionTemplateFactory(name=AUDERE_MAJORA_CONDITION_NAME)
        cls.audere_threshold = AudereThresholdFactory(check_level_bonus=4)
        cls.majora_threshold = AudereMajoraThresholdFactory(
            boundary_level=CHARACTER_LEVEL, check_level_bonus=8
        )

    def setUp(self):
        Trait.flush_instance_cache()
        ResultChart.clear_cache()

    def _level_points(self) -> int:
        return _compute_check_breakdown(
            self.character,
            self.check_type,
            target_difficulty=0,
            extra_modifiers=0,
            effort_level=None,
            fatigue_penalty=0,
            specialization=None,
        ).level_points

    def test_no_audere_counts_own_level(self):
        self.assertEqual(self._level_points(), LEVEL_POINTS_PER_LEVEL * CHARACTER_LEVEL)

    def test_audere_adds_levels(self):
        ConditionInstanceFactory(target=self.character, condition=self.audere_template)
        self.assertEqual(self._level_points(), LEVEL_POINTS_PER_LEVEL * (CHARACTER_LEVEL + 4))

    def test_majora_replaces_audere_bonus(self):
        ConditionInstanceFactory(target=self.character, condition=self.audere_template)
        ConditionInstanceFactory(target=self.character, condition=self.majora_template)
        self.assertEqual(self._level_points(), LEVEL_POINTS_PER_LEVEL * (CHARACTER_LEVEL + 8))


class AudereMajoraThresholdChoiceTests(TestCase):
    """Which Majora threshold's bonus applies, and the fallback when none is reached."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character
        ConditionInstanceFactory(
            target=cls.character, condition=ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        )
        ConditionInstanceFactory(
            target=cls.character,
            condition=ConditionTemplateFactory(name=AUDERE_MAJORA_CONDITION_NAME),
        )
        AudereThresholdFactory(check_level_bonus=4)

    def _bonus_at(self, level: int) -> int:
        with patch(PATH_LEVEL, return_value=level):
            return audere_check_level_bonus(self.character)

    def test_majora_without_a_threshold_at_or_below_level_uses_audere_bonus(self):
        AudereMajoraThresholdFactory(boundary_level=10, check_level_bonus=9)
        self.assertEqual(self._bonus_at(3), 4)

    def test_highest_threshold_at_or_below_level_wins(self):
        AudereMajoraThresholdFactory(boundary_level=5, check_level_bonus=6)
        AudereMajoraThresholdFactory(boundary_level=10, check_level_bonus=9)
        AudereMajoraThresholdFactory(boundary_level=15, check_level_bonus=12)
        self.assertEqual(self._bonus_at(12), 9)
        self.assertEqual(self._bonus_at(15), 12)
