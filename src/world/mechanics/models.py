"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

if TYPE_CHECKING:
    from world.mechanics.models import ModifierType as ModifierTypeType


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


class ModifierSource(models.Model):
    """
    Encapsulates where a character modifier originated from.

    Centralizes source tracking to simplify CharacterModifier and make
    adding new source types easier. Each source links to both the effect
    template (what modifier to apply) and the instance (for cascade deletion).

    The instance FK handles cascade deletion when the source is removed.
    Effect template FKs use SET_NULL to preserve history if templates change.
    At least one field should be set; all null = "unknown" source.
    """

    # === Distinction Source ===
    # Effect template - what modifier type and base value
    distinction_effect = models.ForeignKey(
        "distinctions.DistinctionEffect",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text="The effect template from a distinction",
    )
    # Instance - for cascade deletion when character loses distinction
    character_distinction = models.ForeignKey(
        "distinctions.CharacterDistinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="modifier_sources",
        help_text="The character's distinction that grants this source",
    )

    # === Condition Source ===
    # Note: Conditions use CheckType for check modifiers (ConditionCheckModifier).
    # This FK is for direct ModifierType effects from conditions, if any.
    condition_instance = models.ForeignKey(
        "conditions.ConditionInstance",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="modifier_sources",
        help_text="The condition instance that grants this source",
    )

    # Future: equipment_effect, equipment_instance, spell_effect, etc.

    class Meta:
        verbose_name = "Modifier source"
        verbose_name_plural = "Modifier sources"

    @property
    def modifier_type(self) -> "ModifierTypeType | None":
        """Get the modifier type from the effect template."""
        if self.distinction_effect:
            return self.distinction_effect.target
        return None

    @property
    def source_display(self) -> str:
        """Human-readable source description."""
        if self.distinction_effect:
            return f"Distinction: {self.distinction_effect.distinction.name}"
        if self.condition_instance:
            return f"Condition: {self.condition_instance.condition.name}"
        return "Unknown"

    def __str__(self) -> str:
        return self.source_display


class CharacterModifier(SharedMemoryModel):
    """Actual modifier value on a character, with source tracking.

    Modifiers from various sources (distinctions, equipment, conditions) are
    materialized as records for fast lookup during roll resolution.
    Sources are responsible for creating/deleting their modifier records.

    Stacking: All modifiers stack (sum values for a given modifier_type).
    Display: Hide modifiers with value 0.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Character who has this modifier",
    )
    modifier_type = models.ForeignKey(
        ModifierType,
        on_delete=models.CASCADE,
        related_name="character_modifiers",
        help_text="What type of modifier this is",
    )
    value = models.IntegerField(help_text="Modifier value (can be negative)")

    # Source tracking via ModifierSource
    source = models.ForeignKey(
        ModifierSource,
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Source that grants this modifier",
    )

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

    def __str__(self) -> str:
        return f"{self.character} {self.modifier_type.name}: {self.value:+d} ({self.source})"
