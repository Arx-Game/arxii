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
        unique=True,
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
    description_reversed = models.TextField(
        blank=True,
        default="",
        help_text="Description when the card is drawn reversed.",
    )

    class Meta:
        unique_together: ClassVar[list[tuple[str, ...]]] = [
            ("arcana_type", "suit", "rank"),
        ]
        ordering: ClassVar[list[str]] = ["arcana_type", "suit", "rank"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        if self.arcana_type == ArcanaType.MAJOR and not self.latin_name:
            msg = "Major Arcana cards must have a latin_name."
            raise ValidationError(msg)
        if self.arcana_type == ArcanaType.MINOR and not self.suit:
            msg = "Minor Arcana cards must have a suit."
            raise ValidationError(msg)
        if self.arcana_type == ArcanaType.MAJOR and self.suit:
            msg = "Major Arcana cards should not have a suit."
            raise ValidationError(msg)

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


class NamingRitualConfig(SharedMemoryModel):
    """
    Singleton config for the tarot naming ritual displayed in CG.
    Editable via Django admin. Optional link to a codex entry for lore.
    """

    flavor_text = models.TextField(
        help_text="Flavor text displayed above the tarot card browser in CG.",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional codex entry for 'learn more' link in CG.",
    )

    class Meta:
        verbose_name = "Naming Ritual Configuration"
        verbose_name_plural = "Naming Ritual Configuration"

    def __str__(self) -> str:
        return "Naming Ritual Config"

    def clean(self):
        """Enforce singleton - only one config can exist."""
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        if not self.pk and NamingRitualConfig.objects.exists():
            msg = "Only one NamingRitualConfig can exist."
            raise ValidationError(msg)
