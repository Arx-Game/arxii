"""Tests for CharacterGift and CharacterTechnique models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique


class CharacterGiftModelTest(TestCase):
    """Tests for the CharacterGift model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.gift = GiftFactory(name="Shadow Magic")

    def test_character_gift_creation(self):
        """Test creating a CharacterGift links character sheet to gift."""
        cg = CharacterGift.objects.create(
            character=self.sheet,
            gift=self.gift,
        )

        self.assertEqual(cg.character, self.sheet)
        self.assertEqual(cg.gift, self.gift)
        self.assertIsNotNone(cg.acquired_at)

    def test_unique_together(self):
        """Test that a character cannot have the same gift twice."""
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)

        with self.assertRaises(IntegrityError):
            CharacterGift.objects.create(character=self.sheet, gift=self.gift)

    def test_str_representation(self):
        """Test string representation of CharacterGift."""
        cg = CharacterGift.objects.create(
            character=self.sheet,
            gift=self.gift,
        )

        self.assertIn(str(self.gift), str(cg))
        self.assertIn(str(self.sheet), str(cg))

    def test_factory(self):
        """Test CharacterGiftFactory creates valid instances."""
        cg = CharacterGiftFactory()

        self.assertIsNotNone(cg.character)
        self.assertIsNotNone(cg.gift)
        self.assertIsNotNone(cg.acquired_at)


class CharacterTechniqueModelTest(TestCase):
    """Tests for the CharacterTechnique model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.technique = TechniqueFactory(name="Shadow Bolt")

    def test_character_technique_creation(self):
        """Test creating a CharacterTechnique links character sheet to technique."""
        ct = CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.technique,
        )

        self.assertEqual(ct.character, self.sheet)
        self.assertEqual(ct.technique, self.technique)
        self.assertIsNotNone(ct.acquired_at)

    def test_unique_together(self):
        """Test that a character cannot have the same technique twice."""
        CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)

        with self.assertRaises(IntegrityError):
            CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)

    def test_str_representation(self):
        """Test string representation of CharacterTechnique."""
        ct = CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.technique,
        )

        self.assertIn(str(self.technique), str(ct))
        self.assertIn(str(self.sheet), str(ct))

    def test_factory(self):
        """Test CharacterTechniqueFactory creates valid instances."""
        ct = CharacterTechniqueFactory()

        self.assertIsNotNone(ct.character)
        self.assertIsNotNone(ct.technique)
        self.assertIsNotNone(ct.acquired_at)
