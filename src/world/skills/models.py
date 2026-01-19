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


class CharacterSpecializationValue(SharedMemoryModel):
    """
    Character's specialization value with development tracking.

    Similar to CharacterSkillValue but without rust (specializations are immune).
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="specialization_values",
        help_text="The character this specialization value belongs to",
    )
    specialization = models.ForeignKey(
        Specialization,
        on_delete=models.CASCADE,
        related_name="character_values",
        help_text="The specialization this value is for",
    )
    value = models.PositiveIntegerField(
        help_text="Current specialization value (10, 20, 30, etc.)",
    )
    development_points = models.PositiveIntegerField(
        default=0,
        help_text="Progress toward next level (resets at threshold)",
    )
    character_id: int

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["character", "specialization"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "specialization"]),
            models.Index(fields=["character"]),
        ]

    def __str__(self):
        character = cast("ObjectDB", self.character)
        return f"{character.key}: {self.specialization} = {self.display_value}"

    @property
    def display_value(self) -> float:
        """Display value as shown to players (e.g., 1.5 for value 15)."""
        return round(self.value / 10, 1)


class SkillPointBudget(SharedMemoryModel):
    """
    Configurable CG skill point budget (single-row model).

    Staff can adjust these values without code changes.
    """

    path_points = models.PositiveSmallIntegerField(
        default=50,
        help_text="Points allocated from path suggestions",
    )
    free_points = models.PositiveSmallIntegerField(
        default=60,
        help_text="Points freely allocatable by player",
    )
    points_per_tier = models.PositiveSmallIntegerField(
        default=10,
        help_text="Cost per skill tier (0→10, 10→20, etc.)",
    )
    specialization_unlock_threshold = models.PositiveSmallIntegerField(
        default=30,
        help_text="Parent skill value needed to unlock specializations",
    )
    max_skill_value = models.PositiveSmallIntegerField(
        default=30,
        help_text="Maximum skill value in CG",
    )
    max_specialization_value = models.PositiveSmallIntegerField(
        default=30,
        help_text="Maximum specialization value in CG",
    )

    class Meta:
        verbose_name = "Skill Point Budget"
        verbose_name_plural = "Skill Point Budget"

    def __str__(self):
        return f"Skill Budget: {self.path_points} path + {self.free_points} free"

    @property
    def total_points(self) -> int:
        """Total points available in CG."""
        return self.path_points + self.free_points

    @classmethod
    def get_active_budget(cls) -> "SkillPointBudget":
        """Get the active budget, creating with defaults if none exists."""
        # Use get_or_create with pk=1 for atomic safety (single-row model)
        budget, _ = cls.objects.get_or_create(pk=1)
        return budget


class PathSkillSuggestion(SharedMemoryModel):
    """
    Suggested skill allocation for a path (template only).

    These are defaults that players can freely redistribute.
    The sum of suggested values for a path should equal path_points.
    """

    # Note: field named 'character_class' instead of 'path' because SharedMemoryModel
    # reserves 'path' as a class attribute for the model's module path
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="skill_suggestions",
        help_text="The path (class) this suggestion belongs to",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="path_suggestions",
        help_text="The skill being suggested",
    )
    suggested_value = models.PositiveSmallIntegerField(
        help_text="Suggested starting value (10, 20, or 30)",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Order for display in CG",
    )

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["character_class", "skill"]]
        ordering = ["character_class", "display_order", "skill__trait__name"]

    def __str__(self):
        return f"{self.character_class.name}: {self.skill.name} = {self.suggested_value}"
