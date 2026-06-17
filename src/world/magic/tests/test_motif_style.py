"""Tests for MotifResonanceStyle — per-character style binding.

TDD: written RED-first, then made GREEN by adding the model/factory/serializer.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import StyleFactory
from world.magic.factories import (
    MotifResonanceStyleFactory,
    ResonanceFactory,
)
from world.magic.models import (
    Motif,
    MotifResonance,
    MotifResonanceStyle,
)
from world.magic.serializers import MotifResonanceSerializer


class MotifResonanceStyleModelTests(TestCase):
    """Tests for MotifResonanceStyle — individualization binding."""

    @classmethod
    def setUpTestData(cls):
        """Shared data: two characters, each with their own motif + resonance."""
        cls.char_a = CharacterSheetFactory()
        cls.char_b = CharacterSheetFactory()

        cls.motif_a = Motif.objects.create(character=cls.char_a, description="")
        cls.motif_b = Motif.objects.create(character=cls.char_b, description="")

        cls.resonance_x = ResonanceFactory()
        cls.resonance_y = ResonanceFactory()

        cls.mr_a = MotifResonance.objects.create(motif=cls.motif_a, resonance=cls.resonance_x)
        cls.mr_b = MotifResonance.objects.create(motif=cls.motif_b, resonance=cls.resonance_y)

        cls.seductive = StyleFactory(name="Seductive")
        cls.sinister = StyleFactory(name="Sinister")

    def test_bind_two_styles_to_one_resonance(self):
        """Bind Seductive + Sinister to character A's resonance."""
        s1 = MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.seductive)
        s2 = MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.sinister)
        self.assertEqual(self.mr_a.style_assignments.count(), 2)
        self.assertEqual(s1.style, self.seductive)
        self.assertEqual(s2.style, self.sinister)

    def test_same_style_on_different_character_resonance_is_independent(self):
        """Same Style can be bound to a different character's resonance."""
        MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.seductive)
        # This must NOT raise — different character, different meaning.
        mrs_b = MotifResonanceStyle.objects.create(motif_resonance=self.mr_b, style=self.seductive)
        self.assertEqual(mrs_b.style, self.seductive)

    def test_fourth_style_raises_validation_error(self):
        """MAX_PER_RESONANCE=3: 4th style on one resonance raises ValidationError."""
        styles = [StyleFactory() for _ in range(3)]
        for style in styles:
            MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=style)
        fourth = StyleFactory()
        with self.assertRaises(ValidationError):
            MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=fourth)

    def test_unique_together_same_style_same_resonance(self):
        """Cannot bind the same Style twice to the same resonance."""
        MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.seductive)
        with self.assertRaises(IntegrityError):
            MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.seductive)

    def test_str(self):
        """str representation is informative."""
        mrs = MotifResonanceStyle.objects.create(motif_resonance=self.mr_a, style=self.seductive)
        self.assertIn("Seductive", str(mrs))


class MotifResonanceStyleFactoryTests(TestCase):
    """Tests for MotifResonanceStyleFactory."""

    def test_factory_creates_valid_binding(self):
        """MotifResonanceStyleFactory produces a valid row."""
        mrs = MotifResonanceStyleFactory()
        self.assertIsInstance(mrs, MotifResonanceStyle)
        self.assertIsNotNone(mrs.motif_resonance)
        self.assertIsNotNone(mrs.style)


class MotifResonanceSerializerStyleTests(TestCase):
    """Tests that MotifResonanceSerializer includes style_assignments."""

    @classmethod
    def setUpTestData(cls):
        cls.char = CharacterSheetFactory()
        cls.motif = Motif.objects.create(character=cls.char, description="")
        cls.resonance = ResonanceFactory()
        cls.mr = MotifResonance.objects.create(motif=cls.motif, resonance=cls.resonance)
        cls.style = StyleFactory(name="Radiant")
        MotifResonanceStyle.objects.create(motif_resonance=cls.mr, style=cls.style)

    def test_serializer_includes_style_assignments(self):
        """MotifResonanceSerializer nests style_assignments."""
        data = MotifResonanceSerializer(self.mr).data
        self.assertIn("style_assignments", data)
        self.assertEqual(len(data["style_assignments"]), 1)
        assignment = data["style_assignments"][0]
        self.assertIn("id", assignment)
        self.assertIn("style", assignment)
        self.assertIn("style_name", assignment)
        self.assertEqual(assignment["style_name"], "Radiant")
