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
