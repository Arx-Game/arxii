"""Tests for tarot card models."""

from django.test import TestCase

from world.tarot.constants import ArcanaType, TarotSuit
from world.tarot.models import TarotCard


class TarotCardModelTests(TestCase):
    """Tests for TarotCard model."""

    @classmethod
    def setUpTestData(cls):
        """Create test cards for reuse across tests."""
        cls.major_card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            suit=None,
            rank=0,
            latin_name="Stultus",
        )
        cls.swords_card = TarotCard.objects.create(
            name="Three of Swords",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.SWORDS,
            rank=3,
        )
        cls.cups_card = TarotCard.objects.create(
            name="Ace of Cups",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.CUPS,
            rank=1,
        )
        cls.wands_card = TarotCard.objects.create(
            name="Seven of Wands",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.WANDS,
            rank=7,
        )
        cls.coins_card = TarotCard.objects.create(
            name="King of Coins",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.COINS,
            rank=14,
        )

    def test_str_returns_name(self):
        """__str__ returns the card name."""
        assert str(self.major_card) == "The Fool"
        assert str(self.swords_card) == "Three of Swords"

    def test_major_arcana_upright_surname(self):
        """Major Arcana upright returns latin_name."""
        assert self.major_card.get_surname(is_reversed=False) == "Stultus"

    def test_major_arcana_reversed_surname(self):
        """Major Arcana reversed returns N'-prefixed latin_name."""
        assert self.major_card.get_surname(is_reversed=True) == "N'Stultus"

    def test_swords_upright_surname(self):
        """Minor Arcana Swords upright returns 'Sword'."""
        assert self.swords_card.get_surname(is_reversed=False) == "Sword"

    def test_swords_reversed_surname(self):
        """Minor Arcana Swords reversed returns 'Downsword'."""
        assert self.swords_card.get_surname(is_reversed=True) == "Downsword"

    def test_cups_upright_surname(self):
        """Minor Arcana Cups upright returns 'Cup'."""
        assert self.cups_card.get_surname(is_reversed=False) == "Cup"

    def test_cups_reversed_surname(self):
        """Minor Arcana Cups reversed returns 'Downcup'."""
        assert self.cups_card.get_surname(is_reversed=True) == "Downcup"

    def test_wands_upright_surname(self):
        """Minor Arcana Wands upright returns 'Wand'."""
        assert self.wands_card.get_surname(is_reversed=False) == "Wand"

    def test_wands_reversed_surname(self):
        """Minor Arcana Wands reversed returns 'Downwand'."""
        assert self.wands_card.get_surname(is_reversed=True) == "Downwand"

    def test_coins_upright_surname(self):
        """Minor Arcana Coins upright returns 'Coin'."""
        assert self.coins_card.get_surname(is_reversed=False) == "Coin"

    def test_coins_reversed_surname(self):
        """Minor Arcana Coins reversed returns 'Downcoin'."""
        assert self.coins_card.get_surname(is_reversed=True) == "Downcoin"


class TarotCardDatabaseTests(TestCase):
    """Tests for TarotCard database constraints."""

    def test_create_major_arcana_card(self):
        """Can create a Major Arcana card with no suit."""
        card = TarotCard.objects.create(
            name="The Magician",
            arcana_type=ArcanaType.MAJOR,
            suit=None,
            rank=1,
            latin_name="Magus",
            description="Skill and mastery.",
        )
        card.refresh_from_db()
        assert card.name == "The Magician"
        assert card.arcana_type == ArcanaType.MAJOR
        assert card.suit is None
        assert card.rank == 1
        assert card.latin_name == "Magus"
        assert card.description == "Skill and mastery."

    def test_create_minor_arcana_card(self):
        """Can create a Minor Arcana card with a suit."""
        card = TarotCard.objects.create(
            name="Two of Cups",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.CUPS,
            rank=2,
        )
        card.refresh_from_db()
        assert card.name == "Two of Cups"
        assert card.arcana_type == ArcanaType.MINOR
        assert card.suit == TarotSuit.CUPS
        assert card.rank == 2
        assert card.latin_name == ""
        assert card.description == ""
