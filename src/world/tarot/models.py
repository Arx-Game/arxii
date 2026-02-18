"""
Tarot card models.

Defines the 78-card tarot deck used for surname derivation during character
creation. Familyless characters (orphans, Misbegotten) draw a tarot card
and receive a surname based on that card.
"""

from typing import ClassVar

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.tarot.constants import SUIT_SINGULAR, ArcanaType, TarotSuit


class TarotCard(SharedMemoryModel):
    """
    A single tarot card from the 78-card deck.

    Major Arcana (22 cards): rank 0-21, no suit, have latin_name.
    Minor Arcana (56 cards): rank 1-14, have suit, no latin_name.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name of the card, e.g. 'The Fool' or 'Three of Swords'.",
    )
    arcana_type = models.CharField(
        max_length=5,
        choices=ArcanaType.choices,
        help_text="Whether this card is Major or Minor Arcana.",
    )
    suit = models.CharField(
        max_length=10,
        choices=TarotSuit.choices,
        null=True,
        blank=True,
        help_text="Suit for Minor Arcana cards. Null for Major Arcana.",
    )
    rank = models.PositiveSmallIntegerField(
        help_text="Card rank: 0-21 for Major Arcana, 1-14 for Minor Arcana.",
    )
    latin_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Latin name for Major Arcana cards, used as upright surname.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Flavor text or thematic description of the card.",
    )

    class Meta:
        unique_together: ClassVar[list[tuple[str, ...]]] = [
            ("arcana_type", "suit", "rank"),
        ]
        ordering: ClassVar[list[str]] = ["arcana_type", "suit", "rank"]

    def __str__(self) -> str:
        return self.name

    def get_surname(self, is_reversed: bool) -> str:
        """
        Derive a surname from this card and its orientation.

        Major Arcana upright: latin_name (e.g. "Stultus")
        Major Arcana reversed: N'{latin_name} (e.g. "N'Stultus")
        Minor Arcana upright: singular suit name (e.g. "Sword")
        Minor Arcana reversed: "Down" + lowercase singular (e.g. "Downsword")
        """
        if self.arcana_type == ArcanaType.MAJOR:
            if is_reversed:
                return f"N'{self.latin_name}"
            return self.latin_name

        singular = SUIT_SINGULAR[self.suit]
        if is_reversed:
            return f"Down{singular.lower()}"
        return singular
