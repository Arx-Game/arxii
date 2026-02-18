"""Test tarot fields on CharacterSheet."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class CharacterSheetTarotTest(TestCase):
    """Test tarot card FK and reversed flag on CharacterSheet."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TarotTestChar")
        cls.card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Fatui",
        )

    def test_sheet_with_tarot_card(self):
        """CharacterSheet can store a tarot card and orientation."""
        sheet = CharacterSheet.objects.create(
            character=self.character,
            tarot_card=self.card,
            tarot_reversed=False,
        )
        assert sheet.tarot_card == self.card
        assert sheet.tarot_reversed is False

    def test_sheet_tarot_reversed(self):
        sheet = CharacterSheet.objects.create(
            character=self.character,
            tarot_card=self.card,
            tarot_reversed=True,
        )
        assert sheet.tarot_reversed is True

    def test_sheet_without_tarot(self):
        """CharacterSheet works without tarot (nullable FK)."""
        sheet = CharacterSheet.objects.create(character=self.character)
        assert sheet.tarot_card is None
        assert sheet.tarot_reversed is False
