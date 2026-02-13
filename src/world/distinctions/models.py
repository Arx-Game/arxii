"""
Distinctions system models.

This module contains models for character advantages, disadvantages, and
defining characteristics (merits/flaws equivalent):
- DistinctionCategory: Categories for organizing distinctions
- DistinctionTag: Tags for filtering and search
- Distinction: Individual advantages/disadvantages
- DistinctionEffect: Mechanical effects of distinctions
- DistinctionPrerequisite: Prerequisites for taking distinctions
- DistinctionMutualExclusion: Mutually exclusive distinction pairs
- CharacterDistinction: A character's taken distinctions
- CharacterDistinctionOther: Freeform "Other" entries pending staff mapping
"""

from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.distinctions.types import DistinctionOrigin, OtherStatus


class DistinctionCategoryManager(NaturalKeyManager):
    """Manager for DistinctionCategory with natural key support."""


class DistinctionCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    A category for organizing distinctions.

    Categories are database-defined so new ones can be added via admin.
    The initial set: Physical, Mental, Personality, Social, Background, Arcane.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name for this category.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this category.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what distinctions belong in this category.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in which to display this category (lower = first).",
    )

    objects = DistinctionCategoryManager()

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Distinction Category"
        verbose_name_plural = "Distinction Categories"

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return self.name


class DistinctionTagManager(NaturalKeyManager):
    """Manager for DistinctionTag with natural key support."""


class DistinctionTag(NaturalKeyMixin, SharedMemoryModel):
    """
    A tag for filtering and searching distinctions.

    Tags allow cross-cutting concerns (e.g., "combat-relevant" can tag
    distinctions from multiple categories).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name for this tag.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this tag.",
    )

    objects = DistinctionTagManager()

    class Meta:
        verbose_name = "Distinction Tag"
        verbose_name_plural = "Distinction Tags"

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return self.name


class DistinctionManager(NaturalKeyManager):
    """Manager for Distinction with natural key support."""


class Distinction(NaturalKeyMixin, SharedMemoryModel):
    """
    An individual advantage, disadvantage, or defining characteristic.

    Distinctions are the Arx II equivalent of merits/flaws. They can have
    positive costs (advantages that cost points) or negative costs
    (disadvantages that reimburse points).
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name for this distinction.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this distinction.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this distinction represents.",
    )
    category = models.ForeignKey(
        DistinctionCategory,
        on_delete=models.PROTECT,
        related_name="distinctions",
        help_text="Category this distinction belongs to.",
    )
    cost_per_rank = models.IntegerField(
        default=0,
        help_text="Cost per rank. Positive costs points, negative reimburses.",
    )
    max_rank = models.PositiveIntegerField(
        default=1,
        help_text="Maximum rank. 1 means binary (have it or don't).",
    )

    # Variant system - allows "Noble Blood" to have variants like "Noble Blood (Valardin)"
    parent_distinction = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="variants",
        help_text="Parent distinction if this is a variant.",
    )
    allow_other = models.BooleanField(
        default=False,
        help_text="True if players can specify a custom 'other' value.",
    )
    variants_are_mutually_exclusive = models.BooleanField(
        default=False,
        help_text="If True, only one variant of this parent can be selected per character.",
    )

    # Trust gating - some distinctions require staff trust
    # Non-null trust_value implies trust is required
    trust_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum trust value required to take this distinction.",
    )
    trust_category = models.ForeignKey(
        "stories.TrustCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gated_distinctions",
        help_text="Trust category required to take this distinction.",
    )

    # Mutual exclusions - symmetrical M2M
    mutually_exclusive_with = models.ManyToManyField(
        "self",
        symmetrical=True,
        blank=True,
        help_text="Distinctions that are mutually exclusive with this one.",
    )

    # Automation flags
    is_automatic = models.BooleanField(
        default=False,
        help_text="True if this distinction is automatically granted.",
    )
    requires_slot_filled = models.BooleanField(
        default=False,
        help_text="True if this requires a slot selection to be valid.",
    )

    # Tags for filtering
    tags = models.ManyToManyField(
        DistinctionTag,
        blank=True,
        related_name="distinctions",
        help_text="Tags for filtering and searching.",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this distinction is available for selection.",
    )

    objects = DistinctionManager()

    class Meta:
        verbose_name = "Distinction"
        verbose_name_plural = "Distinctions"

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["distinctions.DistinctionCategory"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_variant_parent(self) -> bool:
        """Check if this distinction has variants (computed from related objects)."""
        return self.variants.exists()

    @property
    def trust_required(self) -> bool:
        """Check if this distinction requires trust (has non-null trust_value)."""
        return self.trust_value is not None

    def calculate_total_cost(self, rank: int) -> int:
        """
        Calculate total cost for a given rank.

        Args:
            rank: The rank to calculate cost for.

        Returns:
            Total cost (cost_per_rank * rank).
        """
        return self.cost_per_rank * rank

    def get_mutually_exclusive(self) -> models.QuerySet["Distinction"]:
        """
        Get all distinctions that are mutually exclusive with this one.

        Returns:
            QuerySet of mutually exclusive distinctions.
        """
        return self.mutually_exclusive_with.all()


class DistinctionPrerequisite(NaturalKeyMixin, SharedMemoryModel):
    """
    A prerequisite rule for taking a distinction.

    Prerequisites are stored as flexible JSON rules supporting:
    - AND, OR, NOT logic
    - Species, beginning, path, distinction, trust checks
    - Nested groups for complex conditions
    """

    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="prerequisites",
        help_text="The distinction this prerequisite belongs to.",
    )
    key = models.CharField(
        max_length=100,
        help_text="Short identifier for this prerequisite (e.g., 'species_check', 'min_rank').",
    )
    rule_json = models.JSONField(
        help_text="JSON structure defining the prerequisite rule with AND/OR/NOT logic.",
    )
    description = models.TextField(
        blank=True,
        help_text="Human-readable description of the prerequisite.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["distinction", "key"]
        dependencies = ["distinctions.Distinction"]

    class Meta:
        unique_together = [("distinction", "key")]
        verbose_name = "Distinction Prerequisite"
        verbose_name_plural = "Distinction Prerequisites"

    def __str__(self) -> str:
        return f"Prerequisite for {self.distinction.name}"


class DistinctionEffect(NaturalKeyMixin, SharedMemoryModel):
    """
    A mechanical effect granted by a distinction.

    Effects modify a specific ModifierType (stats, affinities, resonances, etc.).
    The effect type is now implicit from target.category. Effects can scale
    linearly with rank (value_per_rank) or use custom scaling (scaling_values).
    """

    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="effects",
        help_text="The distinction this effect belongs to.",
    )
    target = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="distinction_effects",
        help_text="The modifier type this effect targets.",
    )
    value_per_rank = models.IntegerField(
        null=True,
        blank=True,
        help_text="Value per rank for linear scaling.",
    )
    scaling_values = models.JSONField(
        null=True,
        blank=True,
        help_text="List of values for non-linear scaling [rank1, rank2, ...].",
    )
    amplifies_sources_by = models.IntegerField(
        null=True,
        blank=True,
        help_text="Bonus to OTHER sources of this modifier type (+2 = all other Allure +2).",
    )
    grants_immunity_to_negative = models.BooleanField(
        default=False,
        help_text="If true, character is immune to negative modifiers of this type.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this effect does.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["distinction", "target"]
        dependencies = ["distinctions.Distinction", "mechanics.ModifierType"]

    class Meta:
        unique_together = ["distinction", "target"]
        verbose_name = "Distinction Effect"
        verbose_name_plural = "Distinction Effects"

    def __str__(self) -> str:
        return f"{self.distinction.name}: {self.target.name}"

    def get_value_at_rank(self, rank: int) -> int:
        """
        Get the effect value at a given rank.

        Args:
            rank: The rank to get the value for (1-indexed).

        Returns:
            The effect value at that rank.
        """
        if self.scaling_values and len(self.scaling_values) >= rank:
            return self.scaling_values[rank - 1]
        if self.value_per_rank is not None:
            return self.value_per_rank * rank
        return 0


class CharacterDistinction(models.Model):
    """
    A distinction granted to a character.

    This is character instance data, NOT a lookup table. It tracks which
    distinctions a character has, at what rank, and how they were acquired.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="distinctions",
        help_text="The character who has this distinction.",
    )
    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The distinction granted to this character.",
    )
    rank = models.PositiveIntegerField(
        default=1,
        help_text="Current rank of this distinction (1 for binary distinctions).",
    )
    notes = models.TextField(
        max_length=280,
        blank=True,
        help_text="Player notes about this distinction.",
    )
    origin = models.CharField(
        max_length=30,
        choices=DistinctionOrigin.choices,
        default=DistinctionOrigin.CHARACTER_CREATION,
        help_text="How this character acquired the distinction.",
    )
    is_temporary = models.BooleanField(
        default=False,
        help_text="Whether this distinction is temporary (e.g., magical effect).",
    )
    source_description = models.TextField(
        blank=True,
        help_text="Description of how the distinction was acquired (for gameplay).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this distinction was granted.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this distinction was last modified.",
    )

    class Meta:
        unique_together = ["character", "distinction"]
        verbose_name = "Character Distinction"
        verbose_name_plural = "Character Distinctions"

    def __str__(self) -> str:
        rank_str = f" (Rank {self.rank})" if self.distinction.max_rank > 1 else ""
        return f"{self.distinction.name}{rank_str} on {self.character}"

    def calculate_total_cost(self) -> int:
        """
        Calculate total cost for this character's distinction at their rank.

        Returns:
            Total cost (cost_per_rank * rank).
        """
        return self.distinction.calculate_total_cost(self.rank)


class CharacterDistinctionOther(models.Model):
    """
    A freeform 'Other' distinction entry pending staff mapping.

    When a player selects 'Other' for a variant distinction, they enter
    freeform text. Staff can then map it to an existing variant or
    create a new one.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="distinction_other_entries",
        help_text="The character who entered this 'Other' distinction.",
    )
    parent_distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="other_entries",
        help_text="The variant parent distinction this 'Other' belongs to.",
    )
    freeform_text = models.CharField(
        max_length=100,
        help_text="What the player entered as their 'Other' value.",
    )
    staff_mapped_distinction = models.ForeignKey(
        Distinction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mapped_from_other",
        help_text="The distinction this was mapped to by staff.",
    )
    status = models.CharField(
        max_length=20,
        choices=OtherStatus.choices,
        default=OtherStatus.PENDING_REVIEW,
        help_text="Current status of this 'Other' entry.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this entry was created.",
    )

    class Meta:
        verbose_name = "Character Distinction Other Entry"
        verbose_name_plural = "Character Distinction Other Entries"

    def __str__(self) -> str:
        return f"'{self.freeform_text}' for {self.parent_distinction.name}"
