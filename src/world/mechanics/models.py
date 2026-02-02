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

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.mechanics.constants import ResonanceAffinity

if TYPE_CHECKING:
    from world.mechanics.models import ModifierType as ModifierTypeType


class ModifierCategoryManager(NaturalKeyManager):
    """Manager for ModifierCategory with natural key support."""


class ModifierCategory(NaturalKeyMixin, SharedMemoryModel):
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

    objects = ModifierCategoryManager()

    class Meta:
        verbose_name_plural = "Modifier categories"
        ordering = ["display_order", "name"]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self):
        return self.name


class ModifierTypeManager(NaturalKeyManager):
    """Manager for ModifierType with natural key support."""


class ModifierType(NaturalKeyMixin, SharedMemoryModel):
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
    affiliated_affinity = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affiliated_resonances",
        help_text="For resonances: the affinity this resonance contributes to.",
    )
    opposite = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opposite_of",
        help_text="For resonances: the opposing resonance in the pair.",
    )
    resonance_affinity = models.CharField(
        max_length=20,
        choices=ResonanceAffinity.choices,
        null=True,
        blank=True,
        help_text="For resonances: celestial, abyssal, or primal.",
    )

    objects = ModifierTypeManager()

    class Meta:
        unique_together = ["category", "name"]
        ordering = ["category__display_order", "display_order", "name"]

    class NaturalKeyConfig:
        fields = ["category", "name"]
        dependencies = ["mechanics.ModifierCategory"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class ModifierSource(models.Model):
    """
    Encapsulates where a character modifier originated from.

    For distinctions, we need BOTH the effect template AND the character instance:
    - distinction_effect: Tells us WHICH modifier type this grants (effect.target)
      and the base value. A Distinction can have multiple effects, so we need
      to know which specific one this source represents.
    - character_distinction: For CASCADE deletion when the character loses the
      distinction. All modifiers from that distinction get cleaned up.

    Future source types (equipment, spells) will follow the same pattern:
    effect template + character instance.
    """

    # === Distinction Source ===
    # Effect template - tells us the modifier_type (via effect.target) and base value
    distinction_effect = models.ForeignKey(
        "distinctions.DistinctionEffect",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text="The effect template (defines modifier_type via effect.target)",
    )
    # Instance - for cascade deletion when character loses distinction
    character_distinction = models.ForeignKey(
        "distinctions.CharacterDistinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="modifier_sources",
        help_text="The character's distinction instance (for cascade deletion)",
    )

    # Future: equipment_effect, equipment_instance, spell_effect, etc.

    class Meta:
        verbose_name = "Modifier source"
        verbose_name_plural = "Modifier sources"

    @property
    def source_type(self) -> str:
        """Get the type of source (distinction, equipment, etc.)."""
        if self.distinction_effect_id or self.character_distinction_id:
            return "distinction"
        return "unknown"

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
        return "Unknown"

    def __str__(self) -> str:
        return self.source_display


class CharacterModifier(SharedMemoryModel):
    """Actual modifier value on a character, with source tracking.

    Modifiers from various sources (distinctions, equipment, conditions) are
    materialized as records for fast lookup during roll resolution.
    Sources are responsible for creating/deleting their modifier records.

    The modifier_type is derived from source.modifier_type (e.g., for distinctions,
    this comes from source.distinction_effect.target). We don't store it directly
    to avoid data duplication and potential inconsistency.

    Stacking: All modifiers stack (sum values for a given modifier_type).
    Display: Hide modifiers with value 0.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Character who has this modifier",
    )
    value = models.IntegerField(help_text="Modifier value (can be negative)")

    # Source tracking via ModifierSource - also provides modifier_type
    source = models.ForeignKey(
        ModifierSource,
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Source that grants this modifier (also defines modifier_type)",
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

    @property
    def modifier_type(self) -> "ModifierTypeType | None":
        """Get the modifier type from the source."""
        return self.source.modifier_type

    def __str__(self) -> str:
        mod_type = self.modifier_type
        type_name = mod_type.name if mod_type else "Unknown"
        return f"{self.character} {type_name}: {self.value:+d} ({self.source})"
