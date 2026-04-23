"""Gifts and Traditions — character magical portfolios and schools.

Gifts are thematic collections of magical techniques.
Traditions represent schools of practice or philosophy.
"""

from functools import cached_property

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.models.affinity import Resonance


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.

    Affinities and Resonances are proper domain models.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this gift.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="gifts",
        help_text="Resonances associated with this gift.",
    )
    creator = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gifts",
        help_text="Character who created this gift.",
    )

    objects = GiftManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_affinity_breakdown(self) -> dict[str, int]:
        """Derive affinity from resonances' affinities."""
        counts: dict[str, int] = {}
        for resonance in self.resonances.select_related("affinity").all():
            aff_name = resonance.affinity.name
            counts[aff_name] = counts.get(aff_name, 0) + 1
        return counts

    @cached_property
    def cached_resonances(self) -> list:
        """Resonances for this gift. Supports Prefetch(to_attr=)."""
        return list(self.resonances.all())

    @cached_property
    def cached_techniques(self) -> list:
        """Techniques for this gift. Supports Prefetch(to_attr=)."""
        return list(self.techniques.all())


class CharacterGift(SharedMemoryModel):
    """
    Links a character to a Gift they know.

    Characters start with one Gift at creation and may learn more
    through play, training, or transformation.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_gifts",
        help_text="The character who knows this gift.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The gift known.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this gift was acquired.",
    )

    class Meta:
        unique_together = ["character", "gift"]
        verbose_name = "Character Gift"
        verbose_name_plural = "Character Gifts"

    def __str__(self) -> str:
        return f"{self.gift} on {self.character}"


class TraditionManager(NaturalKeyManager):
    """Manager for Tradition with natural key support."""


class Tradition(NaturalKeyMixin, SharedMemoryModel):
    """
    A magical tradition representing a school of practice or philosophy.

    Traditions group practitioners who share techniques, beliefs, or methods.
    A tradition may be associated with a society but can also exist independently.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this tradition.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this tradition's philosophy and practices.",
    )
    society = models.ForeignKey(
        "societies.Society",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="traditions",
        help_text="The society this tradition is associated with, if any.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this tradition is currently available for selection.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within lists (lower numbers appear first).",
    )

    objects = TraditionManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Tradition"
        verbose_name_plural = "Traditions"

    def __str__(self) -> str:
        return self.name


class CharacterTradition(SharedMemoryModel):
    """
    Links a character to a tradition they belong to.

    Characters may join traditions during creation or through play.
    A character cannot belong to the same tradition twice.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_traditions",
        help_text="The character who belongs to this tradition.",
    )
    tradition = models.ForeignKey(
        Tradition,
        on_delete=models.PROTECT,
        related_name="character_traditions",
        help_text="The tradition the character belongs to.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the character joined this tradition.",
    )

    class Meta:
        unique_together = ["character", "tradition"]
        verbose_name = "Character Tradition"
        verbose_name_plural = "Character Traditions"

    def __str__(self) -> str:
        return f"{self.tradition} on {self.character}"
