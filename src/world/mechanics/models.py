"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager, CachedAllMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.types import PrerequisiteEvaluation
    from world.traits.models import Trait
from world.mechanics.constants import (
    SOURCE_TYPE_ACHIEVEMENT_REWARD,
    SOURCE_TYPE_DISTINCTION,
    SOURCE_TYPE_FORM,
    SOURCE_TYPE_RESIDENCE_COMFORT,
    SOURCE_TYPE_UNKNOWN,
    ChallengeType,
    DiscoveryType,
    PropertyHolder,
    ResolutionType,
)

_DAMAGE_TYPE_MODEL_PATH = "conditions.DamageType"
_CONSEQUENCE_POOL_MODEL = "actions.ConsequencePool"


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


class ModifierTargetManager(CachedAllMixin, NaturalKeyManager):
    """Manager for ModifierTarget with natural key support, plus cached_all() (#1846)."""


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
        _DAMAGE_TYPE_MODEL_PATH,
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

    # Class-level cache mapping target_trait_id -> ModifierTarget, mirroring
    # Trait._name_to_trait_map. The stat-modifier hot path (TraitHandler.
    # _get_stat_modifier) resolves a ModifierTarget by its target_trait FK
    # per stat read; that lookup is keyed by a non-PK field, so it misses the
    # SharedMemoryModel identity map and re-queries each call. This cache
    # serves it from memory after the first build (#552).
    _trait_cache_built = False
    _trait_to_target_map: dict[int, "ModifierTarget"] = {}

    class Meta:
        unique_together = ["category", "name"]
        ordering = ["category__display_order", "display_order", "name"]

    class NaturalKeyConfig:
        fields = ["category", "name"]
        dependencies = ["mechanics.ModifierCategory"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"

    @classmethod
    def get_for_trait(cls, trait: "Trait") -> "ModifierTarget | None":
        """Return the ModifierTarget whose ``target_trait`` is ``trait`` (cached).

        Keyed by ``target_trait_id`` so repeated stat-modifier lookups don't
        re-query. Returns ``None`` when no target points at the trait.
        """
        if not cls._trait_cache_built:
            cls._build_trait_cache()
        return cls._trait_to_target_map.get(trait.pk)

    @classmethod
    def _build_trait_cache(cls) -> None:
        """Build the target_trait_id -> ModifierTarget mapping."""
        cls._trait_to_target_map = {
            target.target_trait_id: target
            for target in cls.objects.filter(target_trait__isnull=False)
        }
        cls._trait_cache_built = True

    @classmethod
    def clear_trait_cache(cls) -> None:
        """Clear the target_trait cache (call when targets are modified)."""
        cls._trait_cache_built = False
        cls._trait_to_target_map = {}

    def save(self, *args: object, **kwargs: object) -> None:
        """Invalidate the target_trait cache on any ModifierTarget mutation."""
        super().save(*args, **kwargs)
        type(self).clear_trait_cache()

    def delete(self, *args: object, **kwargs: object) -> object:
        """Invalidate the target_trait cache when a target is removed."""
        type(self).clear_trait_cache()
        return super().delete(*args, **kwargs)


class ModifierSource(SharedMemoryModel):
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

    # === Residence Comfort Source (#1514) ===
    # Marks the single shared source for residence-comfort AP-regen modifiers. Comfort has no
    # effect template (it's a computed per-character value), so it's a flag, not an FK pair;
    # ``modifier_target`` stays None (it spans both ap-regen targets) so the target-match
    # validation is skipped. Per-character comfort modifiers cascade-delete via their own
    # ``character`` FK, so this source needs no per-character instance.
    residence_comfort = models.BooleanField(
        default=False,
        help_text="Marks the shared source for residence-comfort AP-regen modifiers (#1514).",
    )

    # === Form Combat Profile Source (slice 4 — alternate self) ===
    form_combat_profile = models.ForeignKey(
        "forms.FormCombatProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text=(
            "The form combat profile this source's modifiers come from (alt-self stat-suite)."
        ),
    )

    # === Achievement Reward Source (#1522) ===
    # Marks the shared source for BONUS rewards granted by achievements (e.g. a +5 allure title).
    # Like residence comfort it carries no effect template — the granted ``CharacterModifier``
    # holds its own ``target``/``value``, and ``modifier_target`` stays None so the target-match
    # validation is skipped. Per-character cleanup is via the modifier's own ``character`` FK.
    achievement_reward = models.BooleanField(
        default=False,
        help_text="Marks the shared source for achievement-granted bonus modifiers.",
    )

    class Meta:
        verbose_name = "Modifier source"
        verbose_name_plural = "Modifier sources"

    @property
    def source_type(self) -> str:
        """Get the type of source (distinction, equipment, etc.)."""
        if self.distinction_effect_id or self.character_distinction_id:
            return SOURCE_TYPE_DISTINCTION
        if self.residence_comfort:
            return SOURCE_TYPE_RESIDENCE_COMFORT
        if self.form_combat_profile_id:
            return SOURCE_TYPE_FORM
        if self.achievement_reward:
            return SOURCE_TYPE_ACHIEVEMENT_REWARD
        return SOURCE_TYPE_UNKNOWN

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
        if self.residence_comfort:
            return "Residence comfort"
        if self.form_combat_profile:
            return f"Form: {self.form_combat_profile}"
        if self.achievement_reward:
            return "Achievement reward"
        return SOURCE_TYPE_UNKNOWN.capitalize()

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
            self.filter(target__pk__in=target_pks)
            .values("character__character_id", "target__pk")
            .annotate(total=models.Sum("value"))
        )

        lookup: dict[int, dict[int, int]] = {}
        for row in rows:
            obj_id = row["character__character_id"]
            target_pk = row["target__pk"]
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

    def clean(self) -> None:
        """Validate that target matches the source's modifier target."""
        source_target = self.source.modifier_target if self.source_id else None
        if source_target and self.target_id and self.target != source_target:
            raise ValidationError({"target": "Target must match the source's modifier target."})

    @property
    def modifier_target(self) -> ModifierTarget:
        """Get the modifier target. Uses the direct FK."""
        return self.target

    def __str__(self) -> str:
        type_name = self.target.name if self.target_id else "Unknown"
        return f"{self.character} {type_name}: {self.value:+d} ({self.source})"


# ---------------------------------------------------------------------------
# Property / Application layer
# ---------------------------------------------------------------------------


class Prerequisite(NaturalKeyMixin, SharedMemoryModel):
    """
    Data-driven property check that gates Capability availability.

    Evaluates whether the property_holder entity has the required Property
    at or above minimum_value. Used at two levels:
    - Capability-level (CapabilityType.prerequisite): checked for ALL sources
    - Source-level (TechniqueCapabilityGrant.prerequisite): per-source check
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.CASCADE,
        related_name="prerequisites",
        help_text="The property to check for on the target entity.",
    )
    property_holder = models.CharField(
        max_length=20,
        choices=PropertyHolder.choices,
        help_text="Which entity to check: character, target object, or location.",
    )
    minimum_value = models.PositiveIntegerField(
        default=1,
        help_text="Minimum property value required. 1 = property must be present.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    def evaluate(
        self,
        character: "ObjectDB",
        target_object: "ObjectDB",
        location: "ObjectDB",
    ) -> "PrerequisiteEvaluation":
        """Evaluate this prerequisite against the current game state."""
        from world.mechanics.types import PrerequisiteEvaluation  # noqa: PLC0415

        entity_map = {
            PropertyHolder.SELF: character,
            PropertyHolder.TARGET: target_object,
            PropertyHolder.LOCATION: location,
        }
        entity = entity_map[self.property_holder]

        obj_prop = ObjectProperty.objects.filter(
            object=entity,
            property=self.property,
        ).first()

        if obj_prop is None:
            return PrerequisiteEvaluation(
                met=False,
                reason=(f"Requires {self.property.name} on {self.get_property_holder_display()}"),
            )

        if obj_prop.value < self.minimum_value:
            return PrerequisiteEvaluation(
                met=False,
                reason=(
                    f"Requires {self.property.name} >="
                    f" {self.minimum_value} on"
                    f" {self.get_property_holder_display()}"
                    f" (current: {obj_prop.value})"
                ),
            )

        return PrerequisiteEvaluation(met=True)


class PropertyCategory(NaturalKeyMixin, SharedMemoryModel):
    """Broad groupings for Properties (e.g., elemental, physical, social)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Property categories"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class Property(NaturalKeyMixin, SharedMemoryModel):
    """
    A neutral descriptive tag on targets or environments.

    Properties describe what something IS, not what can be done to it.
    Examples: flammable, locked, magical, frozen.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        PropertyCategory,
        on_delete=models.CASCADE,
        related_name="properties",
    )

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Properties"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class ChallengeTemplateProperty(SharedMemoryModel):
    """Through model for ChallengeTemplate → Property M2M with value."""

    challenge_template = models.ForeignKey(
        "ChallengeTemplate",
        on_delete=models.CASCADE,
        related_name="challenge_template_properties",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="challenge_template_properties",
    )
    value = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "property"],
                name="challenge_template_property_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.challenge_template.name}: {self.property.name} ({self.value})"


class ObjectProperty(SharedMemoryModel):
    """Runtime property attachment on any game object."""

    object = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="object_properties",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="object_properties",
    )
    value = models.PositiveIntegerField(default=1)
    source_condition = models.ForeignKey(
        "conditions.ConditionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_properties",
    )
    source_challenge = models.ForeignKey(
        "ChallengeInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_properties",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["object", "property"],
                name="object_property_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.object.db_key}: {self.property.name} ({self.value})"


class PropertyDamageModifier(NaturalKeyMixin, SharedMemoryModel):
    """
    Defines how a target's Property modifies damage of a given type.

    Examples:
      - Flammable gives +10 to fire damage
      - Waterlogged gives -20 to lightning damage
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="damage_modifiers",
    )
    damage_type = models.ForeignKey(
        _DAMAGE_TYPE_MODEL_PATH,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="property_damage_modifiers",
        help_text="Specific damage type, or null for ALL damage types",
    )
    modifier_value = models.IntegerField(
        help_text="Modifier to damage (positive = bonus, negative = reduction)",
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "damage_type"],
                name="property_damage_modifier_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["property", "damage_type"]
        dependencies = ["mechanics.Property", _DAMAGE_TYPE_MODEL_PATH]

    def __str__(self) -> str:
        dt_name = self.damage_type.name if self.damage_type else "ALL"
        return f"{self.property.name} -> {self.modifier_value:+d} {dt_name}"


class PropertyDetonation(SharedMemoryModel):
    """Marks a Property as "volatile" — carrying a one-shot detonation payload.

    An object is volatile when it holds an ``ObjectProperty`` whose ``property``
    has a ``PropertyDetonation`` row (see ``Property.detonation``, the OneToOne
    reverse accessor). Combat redirect resolution (#2210) fires
    ``consequence_pool`` against everyone positioned at the volatile object's
    Position when a guardian redirects saved damage into it, then deletes the
    triggering ``ObjectProperty`` row — the volatility is spent, not reusable.
    """

    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name="detonation",
    )
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="property_detonations",
        help_text="Graded/deterministic payload fired against everyone at the object's position.",
    )
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.property.name} (volatile)"


class Application(NaturalKeyMixin, SharedMemoryModel):
    """
    Pure eligibility record: Capability + Property = 'you can attempt this'.

    Applications carry no check type, narrative, or difficulty — those come
    from the delivery mechanism (Technique/tool/trait) and the Situation.
    """

    name = models.CharField(max_length=100)
    capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    target_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="The Property on a Challenge or target that this Application addresses.",
    )
    required_effect_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="required_by_applications",
        help_text="Effect Property the source must carry to use this Application.",
    )
    default_template = models.ForeignKey(
        "mechanics.ChallengeTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_applications",
        help_text=(
            "Authored world-interaction template minted when this Application fires "
            "against a bare object; null = no bare-object affordance"
        ),
    )
    description = models.TextField(blank=True)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Applications"
        constraints = [
            models.UniqueConstraint(
                fields=["capability", "target_property", "name"],
                name="application_unique_cap_prop_name",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.capability.name} + {self.target_property.name})"


# ---------------------------------------------------------------------------
# Trait → Capability derivation
# ---------------------------------------------------------------------------


class TraitCapabilityDerivation(NaturalKeyMixin, SharedMemoryModel):
    """
    Maps a Trait value to a derived Capability value.

    Allows the system to calculate capability levels from character traits
    using a simple linear formula: base_value + (trait_multiplier * trait_value).
    """

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="capability_derivations",
    )
    capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.CASCADE,
        related_name="trait_derivations",
    )
    base_value = models.IntegerField(default=0)
    trait_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["trait", "capability"],
                name="trait_capability_derivation_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["trait", "capability"]
        dependencies = ["traits.Trait", "conditions.CapabilityType"]

    def __str__(self) -> str:
        return f"{self.trait.name} → {self.capability.name}"

    def calculate_value(self, trait_value: int) -> int:
        """Calculate derived capability value from a trait value."""
        return int(self.base_value + (self.trait_multiplier * Decimal(trait_value)))


# ---------------------------------------------------------------------------
# Challenge system
# ---------------------------------------------------------------------------


class ChallengeCategory(NaturalKeyMixin, SharedMemoryModel):
    """Broad groupings for Challenges (e.g., environmental, social, combat)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Challenge categories"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class ChallengeTemplate(NaturalKeyMixin, SharedMemoryModel):
    """
    Reusable blueprint for a Challenge that can be placed in Situations.

    Templates define the structure: what Properties the challenge has,
    how severe it is, what approaches can resolve it, and what consequences
    follow from success or failure.
    """

    name = models.CharField(max_length=100, unique=True)
    description_template = models.TextField(
        blank=True,
        help_text="Template string with {variables} for instance-specific text.",
    )
    properties = models.ManyToManyField(
        Property,
        through="ChallengeTemplateProperty",
        related_name="challenge_templates",
        blank=True,
    )
    severity = models.PositiveIntegerField(default=1)
    goal = models.TextField(blank=True)
    category = models.ForeignKey(
        ChallengeCategory,
        on_delete=models.CASCADE,
        related_name="challenge_templates",
    )
    challenge_type = models.CharField(
        max_length=20,
        choices=ChallengeType.choices,
        default=ChallengeType.INHIBITOR,
    )
    blocked_capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocking_challenges",
    )
    discovery_type = models.CharField(
        max_length=20,
        choices=DiscoveryType.choices,
        default=DiscoveryType.OBVIOUS,
    )
    consequences = models.ManyToManyField(
        "checks.Consequence",
        through="ChallengeTemplateConsequence",
        related_name="challenge_templates",
        blank=True,
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_properties(self) -> list[Property]:
        """Properties on this challenge. Supports Prefetch(to_attr=)."""
        return list(self.properties.all())

    @cached_property
    def cached_approaches(self) -> list["ChallengeApproach"]:
        """Approaches for this challenge. Supports Prefetch(to_attr=)."""
        return list(
            self.approaches.select_related(
                "application__capability",
                "application__target_property",
                "application__required_effect_property",
                "check_type",
                "required_effect_property",
            )
        )

    @cached_property
    def cached_template_properties(self) -> list["ChallengeTemplateProperty"]:
        """Through-model properties. Supports Prefetch(to_attr=)."""
        return list(self.challenge_template_properties.select_related("property"))

    @cached_property
    def cached_consequences(self) -> list["ChallengeTemplateConsequence"]:
        """Through-model consequences. Supports Prefetch(to_attr=)."""
        return list(self.challenge_consequences.select_related("consequence"))


class ChallengeTemplateConsequence(SharedMemoryModel):
    """Through model linking ChallengeTemplate to Consequence with challenge-specific fields."""

    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="challenge_consequences",
    )
    consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.CASCADE,
        related_name="challenge_template_consequences",
    )
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        default=ResolutionType.DESTROY,
    )
    resolution_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "consequence"],
                name="challenge_template_consequence_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.challenge_template.name}: {self.consequence.label}"


class ChallengeApproach(NaturalKeyMixin, SharedMemoryModel):
    """
    A way to resolve a Challenge, linking an Application to a check type.

    This is where the system connects 'what you can do' (Application) with
    'how to resolve it' (CheckType) for a specific Challenge.

    NK is (challenge_template, application) — the existing
    ``challenge_approach_unique_per_template`` constraint already enforces this
    as the true minimal uniqueness (a Challenge offers at most one approach per
    Application), so no new DB constraint was needed to add the natural key.
    """

    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="approaches",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="challenge_approaches",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        related_name="challenge_approaches",
    )
    required_effect_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="required_by_approaches",
    )
    display_name = models.CharField(max_length=100, blank=True)
    custom_description = models.TextField(blank=True)
    action_template = models.ForeignKey(
        "actions.ActionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_approaches",
        help_text="When set, resolution uses this template's check_type and pool.",
    )
    auto_succeeds = models.BooleanField(
        default=False,
        help_text=(
            "When true, this approach skips the roll and lands in the top "
            "outcome tier — the capability trivializes the obstacle."
        ),
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "When true, this approach is offered to every character "
            "regardless of capabilities — the fallback anyone can attempt."
        ),
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "application"],
                name="challenge_approach_unique_per_template",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["challenge_template", "application"]
        dependencies = ["mechanics.ChallengeTemplate", "mechanics.Application"]

    def __str__(self) -> str:
        return self.display_name or self.application.name


class ApproachConsequence(SharedMemoryModel):
    """
    Approach-specific consequence override.

    When an approach has unique outcomes that differ from the template-level
    consequences, they are defined here. Links to a generic Consequence and
    optionally adds challenge-specific resolution_type.
    """

    approach = models.ForeignKey(
        ChallengeApproach,
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.CASCADE,
        related_name="approach_consequences",
    )
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["approach", "consequence"],
                name="approach_consequence_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.approach}: {self.consequence.label}"


# ---------------------------------------------------------------------------
# Situation system
# ---------------------------------------------------------------------------


class SituationTemplate(NaturalKeyMixin, SharedMemoryModel):
    """
    A reusable collection of Challenges that form a coherent scenario.

    GMs place Situations; the system generates player options automatically
    based on the Challenges' Properties and the characters' Capabilities.
    """

    name = models.CharField(max_length=100, unique=True)
    description_template = models.TextField(blank=True)
    challenges = models.ManyToManyField(
        ChallengeTemplate,
        through="SituationChallengeLink",
        related_name="situation_templates",
    )
    category = models.ForeignKey(
        ChallengeCategory,
        on_delete=models.CASCADE,
        related_name="situation_templates",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_challenge_links(self) -> list["SituationChallengeLink"]:
        """Challenge links. Supports Prefetch(to_attr=)."""
        return list(self.challenge_links.select_related("challenge_template"))


class SituationChallengeLink(SharedMemoryModel):
    """Through-table linking Challenges to Situations with ordering and dependencies."""

    situation_template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="challenge_links",
    )
    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="situation_links",
    )
    target_object_name = models.CharField(
        max_length=100,
        help_text=(
            "Display name for the ObjectDB instantiate_situation creates to embody "
            "this challenge (e.g. 'the locked door'). Player-visible via "
            "ChallengeInstanceSerializer.target_object_name."
        ),
    )
    display_order = models.PositiveIntegerField(default=0)
    depends_on = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependents",
    )

    class Meta:
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["situation_template", "challenge_template"],
                name="situation_challenge_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.situation_template.name} → {self.challenge_template.name}"


class SituationTrapLink(SharedMemoryModel):
    """Authored trap blueprint carried by a SituationTemplate.

    Instantiated into a real ``room_features.Trap`` row by
    ``instantiate_situation``. Carries only authorable fields — no
    ``is_armed``/``detected_by`` (always fresh per instantiated Trap), no
    ``position`` (traps minted from a link are always room-wide), no
    ``depends_on`` (traps are independent hazards, not a sequenced chain
    like SituationChallengeLink).
    """

    situation_template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="trap_links",
    )
    name = models.CharField(max_length=100)
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="situation_trap_links",
    )
    detect_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="detect_situation_traps",
    )
    disarm_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="disarm_situation_traps",
    )
    detect_difficulty = models.PositiveIntegerField(default=0)
    disarm_difficulty = models.PositiveIntegerField(default=0)
    is_hidden = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.situation_template.name} — trap: {self.name}"


class SituationInstance(SharedMemoryModel):
    """A live Situation placed at a location, possibly tied to a scene."""

    template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="situation_instances",
    )
    template_variables = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_situations",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="situation_instances",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.template.name} at {self.location.db_key}"


class ChallengeInstance(SharedMemoryModel):
    """A live Challenge at a location, optionally part of a SituationInstance."""

    situation_instance = models.ForeignKey(
        SituationInstance,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="challenge_instances",
    )
    template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="challenge_instances",
    )
    target_object = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="challenge_target_instances",
        help_text="The object embodying this challenge in the world.",
    )
    is_active = models.BooleanField(default=True)
    is_revealed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.template.name} at {self.location.db_key}"


class CharacterChallengeRecord(SharedMemoryModel):
    """Records a character's resolution of a specific Challenge instance."""

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="challenge_records",
    )
    challenge_instance = models.ForeignKey(
        ChallengeInstance,
        on_delete=models.CASCADE,
        related_name="character_records",
    )
    approach = models.ForeignKey(
        ChallengeApproach,
        on_delete=models.CASCADE,
        related_name="character_records",
    )
    outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_records",
    )
    consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_records",
    )
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character", "challenge_instance"],
                name="character_challenge_record_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character.db_key} resolved {self.challenge_instance}"


class ContextConsequencePool(SharedMemoryModel):
    """Links a ConsequencePool to a Property for environmental consequences.

    Rider mode (check_type=null): fires alongside player-initiated actions,
    sharing the action's check result.
    Reactive mode (check_type set): fires without player action using its
    own check type (traps, hazards, environmental effects).
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="context_consequence_pools",
    )
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="context_attachments",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="context_consequence_pools",
        help_text="If set, pool can fire reactively without player action.",
    )
    description = models.TextField(
        blank=True,
        help_text="GM-facing note about this context pool.",
    )

    class Meta:
        verbose_name = "Context Consequence Pool"
        verbose_name_plural = "Context Consequence Pools"
        constraints = [
            models.UniqueConstraint(
                fields=["property", "consequence_pool"],
                name="unique_property_consequence_pool",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.property.name} → {self.consequence_pool.name}"


class AestheticAxisConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning the aesthetic-axis coherence walk (#546).

    Real columns, no JSON. Lazy-created by ``get_aesthetic_config()``; consume
    via that getter rather than direct ORM access.
    """

    objects = ArxSharedMemoryManager()

    base_magnitude = models.PositiveIntegerField(
        default=5,
        help_text="Base bonus (integer) awarded per matched style facet during the coherence walk.",
    )
    full_combination_bonus = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.50"),
        help_text=(
            "Multiplier applied when a resonance's FULL bound style-set is worn. "
            "e.g. 1.50 = 50 %% bonus on top of the summed base magnitudes."
        ),
    )
    perception_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.00"),
        help_text="Max coherence amplification at full perception breadth.",
    )
    perception_breadth_cap = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "Distinct STYLE_PRESENTATION endorsers at which perception amplification saturates."
        ),
    )

    def __str__(self) -> str:
        return "AestheticAxisConfig"  # noqa: STRING_LITERAL - display literal, not an identifier


from world.mechanics.engagement import CharacterEngagement  # noqa: F401, E402
