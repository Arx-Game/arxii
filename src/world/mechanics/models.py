"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class ModifierCategory(SharedMemoryModel):
    """
    Categories for organizing modifier types.

    Examples: stat, magic, affinity, resonance, goal, roll
    These are broad groupings that help organize the unified modifier type registry.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Category name (e.g., 'stat', 'magic', 'affinity')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this category represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    class Meta:
        verbose_name_plural = "Modifier categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class ModifierType(SharedMemoryModel):
    """
    Unified registry of all things that can be modified.

    This replaces the separate Affinity, Resonance, and GoalDomain models
    with a single unified system. Each modifier type belongs to a category
    and can be referenced by the modifier system.
    """

    name = models.CharField(
        max_length=100,
        help_text="Modifier type name",
    )
    category = models.ForeignKey(
        ModifierCategory,
        on_delete=models.CASCADE,
        related_name="types",
        help_text="Category this modifier type belongs to",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this modifier type represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes within category (lower values appear first)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this modifier type is currently active in the game",
    )

    class Meta:
        unique_together = ["category", "name"]
        ordering = ["category__display_order", "display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"
