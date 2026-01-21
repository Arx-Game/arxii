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
