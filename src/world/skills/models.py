"""
Skills System Models

Parent skills and specializations for character abilities.
Skills are linked to the Trait system for unified check resolution.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.models import Trait, TraitType


class Skill(SharedMemoryModel):
    """
    Parent skill definition linked to Trait system.

    Skills are broad categories (Melee Combat, Persuasion) that can have
    specializations underneath them.
    """

    trait = models.OneToOneField(
        Trait,
        on_delete=models.CASCADE,
        limit_choices_to={"trait_type": TraitType.SKILL},
        related_name="skill",
        help_text="The trait definition this skill is linked to",
    )
    tooltip = models.TextField(
        blank=True,
        help_text="Short description shown on hover in UI",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Order for display in character sheets and CG",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this skill is available for use",
    )

    class Meta:
        ordering = ["display_order", "trait__name"]

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """Skill name from linked trait."""
        return self.trait.name

    @property
    def category(self) -> str:
        """Skill category from linked trait."""
        return self.trait.category

    @property
    def description(self) -> str:
        """Skill description from linked trait."""
        return self.trait.description
