"""Tests for the TechniqueDraft model and its payload children."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models import TechniqueDraft


class TechniqueDraftModelTests(TestCase):
    """Model-level tests for TechniqueDraft."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_one_draft_per_character(self) -> None:
        """OneToOneField enforces exactly one draft per CharacterSheet."""
        TechniqueDraft.objects.create(character=self.sheet, name="A")
        with self.assertRaises(IntegrityError):
            TechniqueDraft.objects.create(character=self.sheet, name="B")
