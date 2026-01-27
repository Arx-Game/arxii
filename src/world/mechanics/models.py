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


class CharacterModifier(models.Model):
    """Actual modifier value on a character, with source tracking.

    Modifiers from various sources (distinctions, equipment, conditions) are
    materialized as records for fast lookup during roll resolution.
    Sources are responsible for creating/deleting their modifier records.

    Stacking: All modifiers stack (sum values for a given modifier_type).
    Display: Hide modifiers with value 0.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Character who has this modifier",
    )
    modifier_type = models.ForeignKey(
        ModifierType,
        on_delete=models.CASCADE,
        help_text="What type of modifier this is",
    )
    value = models.IntegerField(help_text="Modifier value (can be negative)")

    # Source tracking - exactly one should be set
    source_distinction = models.ForeignKey(
        "distinctions.CharacterDistinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="granted_modifiers",
        help_text="Distinction that grants this modifier",
    )
    source_condition = models.ForeignKey(
        "conditions.ConditionInstance",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="granted_modifiers",
        help_text="Condition that grants this modifier",
    )
    # Note: source_equipment FK will be added when equipment app exists

    # For temporary modifiers (cologne, spell effects, etc.)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this modifier expires (null = permanent)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Character modifier"
        verbose_name_plural = "Character modifiers"

    def __str__(self):
        source = "unknown"
        if self.source_distinction_id:
            source = f"distinction:{self.source_distinction_id}"
        elif self.source_condition_id:
            source = f"condition:{self.source_condition_id}"
        return f"{self.character} {self.modifier_type.name}: {self.value:+d} ({source})"
