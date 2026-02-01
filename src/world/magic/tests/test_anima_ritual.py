"""Tests for CharacterAnimaRitual and AnimaRitualPerformance models."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    AnimaRitualPerformanceFactory,
    CharacterAnimaRitualFactory,
    ResonanceModifierTypeFactory,
)
from world.magic.models import AnimaRitualPerformance, CharacterAnimaRitual
from world.skills.factories import SkillFactory, SpecializationFactory
from world.traits.factories import TraitFactory
from world.traits.models import TraitType


class CharacterAnimaRitualModelTests(TestCase):
    """Tests for the CharacterAnimaRitual model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.sheet = CharacterSheetFactory()
        cls.stat = TraitFactory(name="Composure", trait_type=TraitType.STAT)
        cls.skill = SkillFactory()
        cls.resonance = ResonanceModifierTypeFactory()

    def test_anima_ritual_creation(self):
        """Test creation of a character anima ritual with all fields."""
        ritual = CharacterAnimaRitual.objects.create(
            character=self.sheet,
            stat=self.stat,
            skill=self.skill,
            resonance=self.resonance,
            description="Sitting quietly, communing with nature.",
        )
        self.assertEqual(ritual.character, self.sheet)
        self.assertEqual(ritual.stat, self.stat)
        self.assertEqual(ritual.skill, self.skill)
        self.assertEqual(ritual.resonance, self.resonance)
        self.assertEqual(ritual.description, "Sitting quietly, communing with nature.")
        self.assertIsNone(ritual.specialization)

    def test_anima_ritual_specialization_is_optional(self):
        """Test that specialization is optional on anima rituals."""
        specialization = SpecializationFactory(parent_skill=self.skill)
        ritual = CharacterAnimaRitual.objects.create(
            character=self.sheet,
            stat=self.stat,
            skill=self.skill,
            specialization=specialization,
            resonance=self.resonance,
            description="A specialized recovery ritual.",
        )
        self.assertEqual(ritual.specialization, specialization)

    def test_anima_ritual_str(self):
        """Test string representation of anima ritual."""
        ritual = CharacterAnimaRitual.objects.create(
            character=self.sheet,
            stat=self.stat,
            skill=self.skill,
            resonance=self.resonance,
            description="Test ritual.",
        )
        self.assertEqual(str(ritual), f"Anima Ritual of {self.sheet}")


class AnimaRitualPerformanceModelTests(TestCase):
    """Tests for the AnimaRitualPerformance model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        cls.stat = TraitFactory(name="Performance Stat", trait_type=TraitType.STAT)
        cls.skill = SkillFactory()
        cls.resonance = ResonanceModifierTypeFactory()
        cls.ritual = CharacterAnimaRitual.objects.create(
            character=cls.sheet,
            stat=cls.stat,
            skill=cls.skill,
            resonance=cls.resonance,
            description="A test ritual.",
        )

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


class CharacterAnimaRitualFactoryTests(TestCase):
    """Tests for the CharacterAnimaRitualFactory."""

    def test_factory_creates_ritual(self):
        """Test that factory creates a valid CharacterAnimaRitual."""
        ritual = CharacterAnimaRitualFactory()
        self.assertIsInstance(ritual, CharacterAnimaRitual)
        self.assertIsNotNone(ritual.character)
        self.assertIsNotNone(ritual.stat)
        self.assertIsNotNone(ritual.skill)
        self.assertIsNotNone(ritual.resonance)
        self.assertTrue(ritual.description)

    def test_factory_without_specialization(self):
        """Test that factory creates ritual without specialization by default."""
        ritual = CharacterAnimaRitualFactory()
        self.assertIsNone(ritual.specialization)


class AnimaRitualPerformanceFactoryTests(TestCase):
    """Tests for the AnimaRitualPerformanceFactory."""

    def test_factory_creates_performance(self):
        """Test that factory creates a valid AnimaRitualPerformance."""
        performance = AnimaRitualPerformanceFactory()
        self.assertIsInstance(performance, AnimaRitualPerformance)
        self.assertIsNotNone(performance.ritual)
        self.assertIsNotNone(performance.target_character)
        self.assertTrue(performance.was_successful)
        self.assertEqual(performance.anima_recovered, 5)

    def test_factory_with_failure(self):
        """Test factory with was_successful=False."""
        performance = AnimaRitualPerformanceFactory(was_successful=False)
        self.assertFalse(performance.was_successful)
        self.assertIsNone(performance.anima_recovered)
