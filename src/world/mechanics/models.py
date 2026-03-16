"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.mechanics.constants import ChallengeType, DiscoveryType, ResolutionType


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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class ChallengeConsequence(models.Model):
    """
    A possible outcome when a Challenge is resolved (or failed).

    Tied to a CheckOutcome tier so consequences scale with roll quality.
    """

    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="challenge_consequences",
    )
    label = models.CharField(max_length=200)
    mechanical_description = models.TextField(blank=True)
    weight = models.PositiveIntegerField(default=1)
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        default=ResolutionType.DESTROY,
    )
    resolution_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    character_loss = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "label"],
                name="challenge_consequence_unique_label",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class ChallengeApproach(models.Model):
    """
    A way to resolve a Challenge, linking an Application to a check type.

    This is where the system connects 'what you can do' (Application) with
    'how to resolve it' (CheckType) for a specific Challenge.
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "application"],
                name="challenge_approach_unique_per_template",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name or self.application.name


class ApproachConsequence(models.Model):
    """
    Approach-specific consequence override.

    When an approach has unique outcomes that differ from the template-level
    consequences, they are defined here. Null/blank fields fall back to
    the template-level ChallengeConsequence.
    """

    approach = models.ForeignKey(
        ChallengeApproach,
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="approach_consequences",
    )
    label = models.CharField(max_length=200)
    mechanical_description = models.TextField(blank=True)
    weight = models.PositiveIntegerField(null=True, blank=True)
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["approach", "label"],
                name="approach_consequence_unique_label",
            ),
        ]

    def __str__(self) -> str:
        return self.label


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


class SituationChallengeLink(models.Model):
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


class SituationInstance(models.Model):
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


class ChallengeInstance(models.Model):
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
    is_active = models.BooleanField(default=True)
    is_revealed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.template.name} at {self.location.db_key}"


class CharacterChallengeRecord(models.Model):
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
