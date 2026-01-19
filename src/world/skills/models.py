"""
Skills System Models

Parent skills and specializations for character abilities.
Skills are linked to the Trait system for unified check resolution.
"""

from typing import TYPE_CHECKING, ClassVar, cast

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.models import Trait, TraitType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


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


class Specialization(SharedMemoryModel):
    """
    Specialization under a parent skill.

    Specializations are specific applications of a skill (e.g., Swords under
    Melee Combat) that stack with the parent when applicable.
    """

    name = models.CharField(
        max_length=100,
        help_text="Specialization name (e.g., 'Swords', 'Seduction')",
    )
    parent_skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="specializations",
        help_text="The parent skill this specialization belongs to",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this specialization covers",
    )
    tooltip = models.TextField(
        blank=True,
        help_text="Short description shown on hover in UI",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Order for display within parent skill",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this specialization is available for use",
    )

    class Meta:
        ordering = ["parent_skill", "display_order", "name"]
        unique_together = ["parent_skill", "name"]

    def __str__(self):
        return f"{self.parent_name}: {self.name}"

    @property
    def parent_name(self) -> str:
        """Parent skill name for display."""
        return self.parent_skill.name


class CharacterSkillValue(SharedMemoryModel):
    """
    Character's skill value with progression tracking.

    Stores the actual skill value plus development points (progress toward
    next level) and rust points (blocks development until cleared).
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="skill_values",
        help_text="The character this skill value belongs to",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="character_values",
        help_text="The skill this value is for",
    )
    value = models.PositiveIntegerField(
        help_text="Current skill value (10, 20, 30, etc.)",
    )
    development_points = models.PositiveIntegerField(
        default=0,
        help_text="Progress toward next level (resets at threshold)",
    )
    rust_points = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated rust blocking development (0 = clear)",
    )
    character_id: int

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["character", "skill"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "skill"]),
            models.Index(fields=["character"]),
        ]

    def __str__(self):
        character = cast("ObjectDB", self.character)
        return f"{character.key}: {self.skill.name} = {self.display_value}"

    @property
    def display_value(self) -> float:
        """Display value as shown to players (e.g., 2.5 for value 25)."""
        return round(self.value / 10, 1)
