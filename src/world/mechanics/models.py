"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class ModifierCategoryManager(NaturalKeyManager):
    """Manager for ModifierCategory with natural key support."""


class ModifierCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    Categories for organizing modifier targets.

    Examples: stat, magic, affinity, resonance, goal, roll
    These are broad groupings that help organize the unified modifier target registry.
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


class ModifierTargetManager(NaturalKeyManager):
    """Manager for ModifierTarget with natural key support."""


class ModifierTarget(NaturalKeyMixin, SharedMemoryModel):
    """
    Unified registry of all things that can be modified.

    This replaces the separate Affinity, Resonance, and GoalDomain models
    with a single unified system. Each modifier target belongs to a category
    and can be referenced by the modifier system.
    """

    name = models.CharField(
        max_length=100,
        help_text="Modifier target name",
    )
    category = models.ForeignKey(
        ModifierCategory,
        on_delete=models.CASCADE,
        related_name="targets",
        help_text="Category this modifier target belongs to",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this modifier target represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes within category (lower values appear first)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this modifier target is currently active in the game",
    )
    target_trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_targets",
        help_text="The trait this target modifies. Populated for stat category; "
        "null for categories whose target systems aren't built yet. "
        "See TECH_DEBT.md for tracking.",
    )
    target_affinity = models.OneToOneField(
        "magic.Affinity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The affinity this target represents (affinity category only).",
    )
    target_resonance = models.OneToOneField(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The resonance this target represents (resonance category only).",
    )
    target_capability = models.OneToOneField(
        "conditions.CapabilityType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The capability this target represents (capability category only).",
    )
    target_check_type = models.OneToOneField(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The check type this target represents (check category only).",
    )
    target_damage_type = models.OneToOneField(
        "conditions.DamageType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The damage type this target represents (resistance category only).",
    )
    # Future target FKs — added when their systems are built:
    # target_condition: FK to conditions.ConditionTemplate — condition modifier system
    # See TECH_DEBT.md §"Future Target FKs" for full tracking list.
    objects = ModifierTargetManager()

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
    - distinction_effect: Tells us WHICH modifier target this grants (effect.target)
      and the base value. A Distinction can have multiple effects, so we need
      to know which specific one this source represents.
    - character_distinction: For CASCADE deletion when the character loses the
      distinction. All modifiers from that distinction get cleaned up.

    Future source types (equipment, spells) will follow the same pattern:
    effect template + character instance.
    """

    # === Distinction Source ===
    # Effect template - tells us the modifier_target (via effect.target) and base value
    distinction_effect = models.ForeignKey(
        "distinctions.DistinctionEffect",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text="The effect template (defines modifier_target via effect.target)",
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
    def modifier_target(self) -> ModifierTarget | None:
        """Get the modifier target from the effect template."""
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


class CharacterModifierQuerySet(models.QuerySet):
    """Custom queryset for CharacterModifier with batch aggregation methods."""

    def totals_by_character_for_targets(
        self,
        targets: list["ModifierTarget"],
    ) -> dict[int, dict[int, int]]:
        """Aggregate modifier totals grouped by character's ObjectDB id and target pk.

        Single query regardless of character count. Returns:
            {object_db_id: {modifier_target_pk: total_value}}
        """
        if not targets:
            return {}

        target_pks = [t.pk for t in targets]
        rows = (
            self.filter(source__distinction_effect__target__pk__in=target_pks)
            .values("character__character_id", "source__distinction_effect__target__pk")
            .annotate(total=models.Sum("value"))
        )

        lookup: dict[int, dict[int, int]] = {}
        for row in rows:
            obj_id = row["character__character_id"]
            target_pk = row["source__distinction_effect__target__pk"]
            lookup.setdefault(obj_id, {})[target_pk] = row["total"]
        return lookup


class CharacterModifier(SharedMemoryModel):
    """Actual modifier value on a character, with source tracking.

    Modifiers from various sources (distinctions, equipment, conditions) are
    materialized as records for fast lookup during roll resolution.
    Sources are responsible for creating/deleting their modifier records.

    Each modifier has a direct ``target`` FK to ModifierTarget (what it modifies)
    and a ``source`` FK to ModifierSource (where it came from). The target is set
    once at creation and never changes.

    Stacking: All modifiers stack (sum values for a given target).
    Display: Hide modifiers with value 0.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Character who has this modifier",
    )
    target = models.ForeignKey(
        ModifierTarget,
        on_delete=models.CASCADE,
        related_name="character_modifiers",
        help_text="What this modifier affects (e.g., strength, ap_daily_regen).",
    )
    value = models.IntegerField(help_text="Modifier value (can be negative)")

    # Source tracking — provenance and cascade deletion
    source = models.ForeignKey(
        ModifierSource,
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Where this modifier came from (for cascade deletion and display).",
    )

    # For temporary modifiers (cologne, spell effects, etc.)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this modifier expires (null = permanent)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = CharacterModifierQuerySet.as_manager()  # type: ignore[assignment]

    class Meta:
        verbose_name = "Character modifier"
        verbose_name_plural = "Character modifiers"

    @property
    def modifier_target(self) -> ModifierTarget | None:
        """Get the modifier target. Uses the direct FK."""
        return self.target

    def __str__(self) -> str:
        type_name = self.target.name if self.target_id else "Unknown"
        return f"{self.character} {type_name}: {self.value:+d} ({self.source})"
