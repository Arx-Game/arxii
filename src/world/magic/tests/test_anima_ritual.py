"""Tests for AnimaRitualPerformance model and related factories.

The per-character anima ritual is now modelled as a Ritual row with
execution_kind=SCENE_ACTION and a RitualSceneActionConfig sidecar.
CharacterAnimaRitual has been deleted.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    AnimaRitualPerformanceFactory,
    ResonanceFactory,
    RitualFactory,
    RitualSceneActionConfigFactory,
)
from world.magic.models import AnimaRitualPerformance, Ritual, RitualSceneActionConfig
from world.skills.factories import SkillFactory, SpecializationFactory
from world.traits.factories import TraitFactory
from world.traits.models import TraitType


class RitualSceneActionConfigModelTests(TestCase):
    """Tests for the RitualSceneActionConfig model (replaces CharacterAnimaRitual tests)."""

    @classmethod
    def setUpTestData(cls):
        cls.stat = TraitFactory(name="Composure", trait_type=TraitType.STAT)
        cls.skill = SkillFactory()
        cls.resonance = ResonanceFactory()
        cls.check_type = CheckTypeFactory()
        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )

    def test_scene_action_config_creation(self):
        """Test creation of a RitualSceneActionConfig with all fields."""
        config = RitualSceneActionConfig.objects.create(
            ritual=self.ritual,
            stat=self.stat,
            skill=self.skill,
            resonance=self.resonance,
            check_type=self.check_type,
        )
        self.assertEqual(config.ritual, self.ritual)
        self.assertEqual(config.stat, self.stat)
        self.assertEqual(config.skill, self.skill)
        self.assertEqual(config.resonance, self.resonance)
        self.assertEqual(config.check_type, self.check_type)
        self.assertIsNone(config.specialization)

    def test_scene_action_config_specialization_optional(self):
        """Test that specialization is optional on RitualSceneActionConfig."""
        specialization = SpecializationFactory(parent_skill=self.skill)
        config = RitualSceneActionConfig.objects.create(
            ritual=RitualFactory(
                execution_kind=RitualExecutionKind.SCENE_ACTION,
                service_function_path="",
                flow=None,
            ),
            stat=self.stat,
            skill=self.skill,
            specialization=specialization,
            resonance=self.resonance,
            check_type=self.check_type,
        )
        self.assertEqual(config.specialization, specialization)

    def test_ritual_str(self):
        """Ritual str() returns the ritual name."""
        self.assertEqual(str(self.ritual), self.ritual.name)


class AnimaRitualPerformanceModelTests(TestCase):
    """Tests for the AnimaRitualPerformance model."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        RitualSceneActionConfigFactory(ritual=cls.ritual)

    def test_performance_creation(self):
        """Test creation of a ritual performance with all fields."""
        performance = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=True,
            anima_recovered=5,
        )
        self.assertEqual(performance.ritual, self.ritual)
        self.assertEqual(performance.target_character, self.target_sheet)
        self.assertTrue(performance.was_successful)
        self.assertEqual(performance.anima_recovered, 5)
        self.assertIsNotNone(performance.performed_at)
        self.assertIsNone(performance.scene)
        self.assertEqual(performance.notes, "")

    def test_performance_without_scene(self):
        """Test that scene is optional on performances."""
        performance = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=False,
        )
        self.assertIsNone(performance.scene)
        self.assertFalse(performance.was_successful)

    def test_performance_str_success(self):
        """Test string representation for successful performance."""
        performance = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=True,
            anima_recovered=5,
        )
        expected = f"{self.ritual} (success) at {performance.performed_at}"
        self.assertEqual(str(performance), expected)

    def test_performance_str_failure(self):
        """Test string representation for failed performance."""
        performance = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=False,
        )
        expected = f"{self.ritual} (failure) at {performance.performed_at}"
        self.assertEqual(str(performance), expected)

    def test_performance_ordering(self):
        """Test that performances are ordered by performed_at descending."""
        performance1 = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=True,
        )
        performance2 = AnimaRitualPerformance.objects.create(
            ritual=self.ritual,
            target_character=self.target_sheet,
            was_successful=True,
        )
        performances = list(AnimaRitualPerformance.objects.all())
        # Most recent should be first
        self.assertEqual(performances[0], performance2)
        self.assertEqual(performances[1], performance1)


class AnimaRitualPerformanceFactoryTests(TestCase):
    """Tests for the AnimaRitualPerformanceFactory."""

    def test_factory_creates_performance(self):
        """Test that factory creates a valid AnimaRitualPerformance."""
        performance = AnimaRitualPerformanceFactory()
        self.assertIsInstance(performance, AnimaRitualPerformance)
        self.assertIsNotNone(performance.ritual)
        self.assertIsInstance(performance.ritual, Ritual)
        self.assertEqual(performance.ritual.execution_kind, RitualExecutionKind.SCENE_ACTION)
        self.assertIsNotNone(performance.target_character)
        self.assertTrue(performance.was_successful)
        self.assertEqual(performance.anima_recovered, 5)

    def test_factory_with_failure(self):
        """Test factory with was_successful=False."""
        performance = AnimaRitualPerformanceFactory(was_successful=False)
        self.assertFalse(performance.was_successful)
        self.assertIsNone(performance.anima_recovered)
