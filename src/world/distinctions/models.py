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
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.distinctions.types import EffectType


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
    is_variant_parent = models.BooleanField(
        default=False,
        help_text="True if this distinction has variants to choose from.",
    )
    allow_other = models.BooleanField(
        default=False,
        help_text="True if players can specify a custom 'other' value.",
    )

    # Trust gating - some distinctions require staff trust
    trust_required = models.BooleanField(
        default=False,
        help_text="True if this distinction requires trust to take.",
    )
    trust_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum trust value required if trust_required is True.",
    )
    trust_category = models.ForeignKey(
        "stories.TrustCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gated_distinctions",
        help_text="Trust category required if trust_required is True.",
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

    def calculate_total_cost(self, rank: int) -> int:
        """
        Calculate total cost for a given rank.

        Args:
            rank: The rank to calculate cost for.

        Returns:
            Total cost (cost_per_rank * rank).
        """
        return self.cost_per_rank * rank


class DistinctionPrerequisite(SharedMemoryModel):
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
    rule_json = models.JSONField(
        help_text="JSON structure defining the prerequisite rule with AND/OR/NOT logic.",
    )
    description = models.TextField(
        blank=True,
        help_text="Human-readable description of the prerequisite.",
    )

    class Meta:
        verbose_name = "Distinction Prerequisite"
        verbose_name_plural = "Distinction Prerequisites"

    def __str__(self) -> str:
        return f"Prerequisite for {self.distinction.name}"


class DistinctionMutualExclusion(SharedMemoryModel):
    """
    A pair of mutually exclusive distinctions.

    If a character has one, they cannot take the other (but it's visible
    and shown as locked with explanation).
    """

    distinction_a = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="exclusions_as_a",
        help_text="First distinction in the mutual exclusion pair.",
    )
    distinction_b = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="exclusions_as_b",
        help_text="Second distinction in the mutual exclusion pair.",
    )

    class Meta:
        unique_together = ["distinction_a", "distinction_b"]
        verbose_name = "Distinction Mutual Exclusion"
        verbose_name_plural = "Distinction Mutual Exclusions"

    def __str__(self) -> str:
        return f"{self.distinction_a.name} <-> {self.distinction_b.name}"

    @classmethod
    def get_excluded_for(cls, distinction: Distinction) -> list[Distinction]:
        """
        Get all distinctions that are mutually exclusive with the given distinction.

        Args:
            distinction: The distinction to check exclusions for.

        Returns:
            List of distinctions that are mutually exclusive with this one.
        """
        exclusions_as_a = cls.objects.filter(distinction_a=distinction).select_related(
            "distinction_b"
        )
        exclusions_as_b = cls.objects.filter(distinction_b=distinction).select_related(
            "distinction_a"
        )

        excluded = [exc.distinction_b for exc in exclusions_as_a]
        excluded.extend([exc.distinction_a for exc in exclusions_as_b])
        return excluded


class DistinctionEffect(SharedMemoryModel):
    """
    A mechanical effect granted by a distinction.

    Effects can modify stats, affinities, resonances, roll outcomes, or be
    code-handled for special behaviors. Effects can scale linearly with rank
    (value_per_rank) or use custom scaling (scaling_values).
    """

    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="effects",
        help_text="The distinction this effect belongs to.",
    )
    effect_type = models.CharField(
        max_length=30,
        choices=EffectType.choices,
        help_text="The type of mechanical effect.",
    )
    target = models.CharField(
        max_length=100,
        blank=True,
        help_text="What this effect targets (e.g., 'allure', 'strength').",
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
    slug_reference = models.SlugField(
        max_length=100,
        blank=True,
        help_text="Reference slug for code-handled effects.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this effect does.",
    )

    class Meta:
        verbose_name = "Distinction Effect"
        verbose_name_plural = "Distinction Effects"

    def __str__(self) -> str:
        return f"{self.distinction.name}: {self.get_effect_type_display()}"

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
