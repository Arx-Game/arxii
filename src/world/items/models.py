"""Models for items, equipment, and inventory."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class QualityTier(SharedMemoryModel):
    """
    Discrete quality level for items, reusable across systems.

    Color-coded tiers (e.g., Common=white, Fine=green, Masterwork=purple)
    provide consistent visual language for quality/difficulty throughout the game.
    """

    name = models.CharField(max_length=50, unique=True)
    color_hex = models.CharField(
        max_length=7,
        help_text="Hex color code for UI display (e.g., '#00FF00').",
    )
    numeric_min = models.PositiveIntegerField(
        help_text="Lower bound of the internal numeric quality range.",
    )
    numeric_max = models.PositiveIntegerField(
        help_text="Upper bound of the internal numeric quality range.",
    )
    stat_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text="Multiplier applied to base stats for items of this tier.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering (lower = worse quality).",
    )

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.name


class InteractionType(SharedMemoryModel):
    """
    An action that can be performed on an item (eat, drink, read, wield, etc.).

    Item templates declare supported interactions via M2M. Adding new interaction
    types requires only a new DB row, not code changes.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal identifier (e.g., 'eat', 'wield', 'study').",
    )
    label = models.CharField(
        max_length=50,
        help_text="Player-facing label (e.g., 'Eat', 'Wield', 'Study').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this interaction does.",
    )

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label
