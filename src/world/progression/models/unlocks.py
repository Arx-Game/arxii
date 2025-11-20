"""
Unlock models for the progression system.

This module contains models related to unlocks and requirements:
- XP cost system: XPCostChart, XPCostEntry, ClassXPCost, TraitXPCost
- Unlock types: ClassLevelUnlock, TraitRatingUnlock, EliteClassUnlock
- Requirements: AbstractRequirement and all concrete requirement types
- Character unlocks: CharacterUnlock
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

# XP Cost System

# Cost modifier constants
NORMAL_COST_PERCENTAGE = 100

# Rating validation constants
RATING_DIVISOR = 10

# Tier calculation constants
TIER_ONE_MAX_LEVEL = 5


class XPCostChart(SharedMemoryModel):
    """
    XP cost charts that apply to multiple classes/traits.

    Instead of having individual cost entries per class/level, we have charts
    that define the cost curve and then apply them to many classes/traits.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name for this cost chart",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of when to use this chart",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this chart is active",
    )

    def get_cost_for_level(self, level):
        """Get the XP cost for a specific level from this chart."""
        try:
            cost_entry = self.cost_entries.get(level=level)
            return cost_entry.xp_cost
        except XPCostEntry.DoesNotExist:
            return 0  # No cost defined

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class XPCostEntry(models.Model):
    """Individual level/cost entries within an XP cost chart."""

    chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="cost_entries",
    )
    level = models.PositiveIntegerField(
        help_text="Level (for classes) or rating threshold (for traits)",
    )
    xp_cost = models.PositiveIntegerField(help_text="XP cost for this level/rating")

    class Meta:
        unique_together = ["chart", "level"]
        ordering = ["chart", "level"]

    def __str__(self):
        return f"{self.chart.name} Level {self.level}: {self.xp_cost} XP"


class ClassXPCost(models.Model):
    """
    Links classes to XP cost charts with optional modifiers.

    This allows most classes to use standard cost charts, but some elite classes
    can have cost modifiers (e.g., 1.5x more expensive).
    """

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="xp_costs",
    )
    cost_chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="class_costs",
    )
    cost_modifier = models.PositiveIntegerField(
        default=NORMAL_COST_PERCENTAGE,
        help_text="Cost modifier as percentage (100 = normal, "
        "150 = 50% more expensive, 80 = 20% cheaper)",
    )

    def get_cost_for_level(self, level):
        """Get the modified XP cost for this class at a specific level."""
        base_cost = self.cost_chart.get_cost_for_level(level)
        return int(base_cost * self.cost_modifier / NORMAL_COST_PERCENTAGE)

    class Meta:
        unique_together = ["character_class", "cost_chart"]

    def __str__(self):
        modifier_str = (
            f" ({self.cost_modifier}%)"
            if self.cost_modifier != NORMAL_COST_PERCENTAGE
            else ""
        )
        return f"{self.character_class.name}: {self.cost_chart.name}{modifier_str}"


class TraitXPCost(models.Model):
    """
    Links traits to XP cost charts with optional modifiers.

    Similar to ClassXPCost but for trait rating thresholds.
    """

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="xp_costs",
    )
    cost_chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="trait_costs",
    )
    cost_modifier = models.PositiveIntegerField(
        default=NORMAL_COST_PERCENTAGE,
        help_text="Cost modifier as percentage (100 = normal, "
        "150 = 50% more expensive, 80 = 20% cheaper)",
    )

    def get_cost_for_rating(self, rating):
        """Get the modified XP cost for this trait at a specific rating."""
        base_cost = self.cost_chart.get_cost_for_level(rating)
        return int(base_cost * self.cost_modifier / NORMAL_COST_PERCENTAGE)

    class Meta:
        unique_together = ["trait", "cost_chart"]

    def __str__(self):
        modifier_str = (
            f" ({self.cost_modifier}%)"
            if self.cost_modifier != NORMAL_COST_PERCENTAGE
            else ""
        )
        return f"{self.trait.name}: {self.cost_chart.name}{modifier_str}"


# Unlock Types


class ClassLevelUnlock(models.Model):
    """Unlocking a new level in a character class."""

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="level_unlocks",
    )
    target_level = models.PositiveIntegerField(help_text="Level being unlocked")

    def get_xp_cost_for_character(self, character):
        """Get the XP cost for this unlock for a specific character."""
        try:
            class_xp_cost = ClassXPCost.objects.get(
                character_class=self.character_class,
            )
            return class_xp_cost.get_cost_for_level(self.target_level)
        except ClassXPCost.DoesNotExist:
            return 0  # No cost defined

    class Meta:
        unique_together = ["character_class", "target_level"]
        ordering = ["character_class", "target_level"]

    def __str__(self):
        return f"{self.character_class.name} Level {self.target_level}"


class TraitRatingUnlock(models.Model):
    """Unlocking a major trait rating threshold."""

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="rating_unlocks",
    )
    target_rating = models.PositiveIntegerField(
        help_text="Rating being unlocked (should be divisible by 10)",
    )

    def get_xp_cost_for_character(self, character):
        """Get the XP cost for this unlock for a specific character."""
        try:
            trait_xp_cost = TraitXPCost.objects.get(trait=self.trait)
            return trait_xp_cost.get_cost_for_rating(self.target_rating)
        except TraitXPCost.DoesNotExist:
            return 0  # No cost defined

    def clean(self):
        """Validate that target_rating is divisible by 10."""
        super().clean()
        if self.target_rating % RATING_DIVISOR != 0:
            msg = "Target rating should be divisible by 10"
            raise ValidationError(msg)

    class Meta:
        unique_together = ["trait", "target_rating"]
        ordering = ["trait", "target_rating"]

    def __str__(self):
        return f"{self.trait.name} Rating {self.target_rating / RATING_DIVISOR:.1f}"


# Abstract Requirements System


class AbstractClassLevelRequirement(models.Model):
    """Abstract base for all types of requirements for class level unlocks."""

    description = models.TextField(
        blank=True,
        help_text="Description of this requirement",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this requirement is active",
    )

    # Direct foreign key to the class level unlock this requirement applies to
    class_level_unlock = models.ForeignKey(
        "ClassLevelUnlock",
        on_delete=models.CASCADE,
        related_name="%(class)s_requirements",
    )

    class Meta:
        abstract = True

    def is_met_by_character(self, character):
        """Check if this requirement is met by the given character."""
        msg = "Subclasses must implement is_met_by_character"
        raise NotImplementedError(msg)


class TraitRequirement(AbstractClassLevelRequirement):
    """Requirement for a specific trait at a minimum value."""

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="trait_requirements",
    )
    minimum_value = models.PositiveIntegerField(
        help_text="Minimum trait value required",
    )

    def is_met_by_character(self, character):
        """Check if character has the required trait value."""
        try:
            from world.traits.models import CharacterTraitValue

            trait_value = CharacterTraitValue.objects.get(
                character=character,
                trait=self.trait,
            )
            if trait_value.value >= self.minimum_value:
                return (
                    True,
                    f"Has {self.trait.name} {trait_value.display_value}",
                )
            return (
                False,
                f"Need {self.trait.name} {self.minimum_value / RATING_DIVISOR:.1f}, "
                f"have {trait_value.display_value}",
            )
        except Exception:
            return (
                False,
                (
                    f"Need {self.trait.name} "
                    f"{self.minimum_value / RATING_DIVISOR:.1f}, trait not set"
                ),
            )

    def __str__(self):
        return f"Trait: {self.trait.name} >= {self.minimum_value / RATING_DIVISOR:.1f}"


class LevelRequirement(AbstractClassLevelRequirement):
    """Requirement for a minimum character level."""

    minimum_level = models.PositiveIntegerField(
        help_text="Minimum character level required",
    )

    def is_met_by_character(self, character):
        """Check if character meets the level requirement."""
        character_levels = character.character_class_levels.all()
        if not character_levels.exists():
            return False, "Character has no class levels"

        highest_level = max(ccl.level for ccl in character_levels)
        if highest_level >= self.minimum_level:
            return True, f"Character is level {highest_level}"
        return (
            False,
            f"Need level {self.minimum_level}, character is {highest_level}",
        )

    def __str__(self):
        return f"Level: >= {self.minimum_level}"


class ClassLevelRequirement(AbstractClassLevelRequirement):
    """Requirement for a specific level in a specific class."""

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
    )
    minimum_level = models.PositiveIntegerField(
        help_text="Minimum level required in this class",
    )

    def is_met_by_character(self, character):
        """Check if character has the required level in the specific class."""
        try:
            class_level = character.character_class_levels.get(
                character_class=self.character_class,
            )
            if class_level.level >= self.minimum_level:
                return (
                    True,
                    f"Has {self.character_class.name} level {class_level.level}",
                )
            return (
                False,
                f"Need {self.character_class.name} level {self.minimum_level}, "
                f"have {class_level.level}",
            )
        except Exception:
            return (
                False,
                f"Need {self.character_class.name} level {self.minimum_level}, "
                "don't have class",
            )

    def __str__(self):
        return f"Class Level: {self.character_class.name} >= {self.minimum_level}"


class MultiClassRequirement(AbstractClassLevelRequirement):
    """Requirement for having multiple classes at specific levels."""

    required_classes = models.ManyToManyField(
        "classes.CharacterClass",
        through="MultiClassLevel",
        related_name="multi_requirements",
    )
    description_override = models.CharField(
        max_length=255,
        blank=True,
        help_text="Override description (e.g., 'Two different classes at level 6+')",
    )

    def is_met_by_character(self, character):
        """Check if character meets the multi-class requirements."""
        character_levels = {
            ccl.character_class: ccl.level
            for ccl in character.character_class_levels.all()
        }

        met_requirements = 0
        required_count = self.class_levels.count()

        for mcl in self.class_levels.all():
            if character_levels.get(mcl.character_class, 0) >= mcl.minimum_level:
                met_requirements += 1

        if met_requirements >= required_count:
            return (
                True,
                f"Has {met_requirements}/{required_count} required class levels",
            )
        return (
            False,
            f"Need {required_count} class requirements, have {met_requirements}",
        )

    def __str__(self):
        if self.description_override:
            return self.description_override
        return f"Multi-class requirement with {self.class_levels.count()} classes"


class MultiClassLevel(models.Model):
    """Through model for multi-class requirements."""

    multi_class_requirement = models.ForeignKey(
        MultiClassRequirement,
        on_delete=models.CASCADE,
        related_name="class_levels",
    )
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
    )
    minimum_level = models.PositiveIntegerField(
        help_text="Minimum level required in this class",
    )

    class Meta:
        unique_together = ["multi_class_requirement", "character_class"]


class AchievementRequirement(AbstractClassLevelRequirement):
    """Requirement based on character achievements or story progress."""

    achievement_key = models.CharField(
        max_length=100,
        help_text="Key identifying the achievement/story flag required",
    )

    def is_met_by_character(self, character):
        """Check if character has the required achievement."""
        if hasattr(character.db, self.achievement_key):
            return True, f"Has achievement: {self.achievement_key}"
        return False, f"Missing achievement: {self.achievement_key}"

    def __str__(self):
        return f"Achievement: {self.achievement_key}"


class RelationshipRequirement(AbstractClassLevelRequirement):
    """Requirement based on character relationships."""

    relationship_target = models.CharField(
        max_length=100,
        help_text="Target of the relationship",
    )
    minimum_level = models.PositiveIntegerField(
        help_text="Minimum relationship level required",
    )

    def is_met_by_character(self, character):
        """Check if character has the required relationship level."""
        return (
            False,
            f"Need relationship with {self.relationship_target} at level "
            f"{self.minimum_level}",
        )

    def __str__(self):
        return f"Relationship: {self.relationship_target} >= {self.minimum_level}"


class TierRequirement(AbstractClassLevelRequirement):
    """Requirement for a character to have reached a specific tier in any class."""

    minimum_tier = models.PositiveIntegerField(
        help_text="Minimum tier required (1 for levels 1-5, 2 for levels 6-10)",
    )

    def is_met_by_character(self, character):
        """Check if character has reached the required tier in any class."""
        character_levels = character.character_class_levels.all()
        if not character_levels.exists():
            return False, "Character has no class levels"

        highest_level = max(ccl.level for ccl in character_levels)
        character_tier = 1 if highest_level <= TIER_ONE_MAX_LEVEL else 2

        if character_tier >= self.minimum_tier:
            return True, f"Character is tier {character_tier} (level {highest_level})"
        return (
            False,
            f"Need tier {self.minimum_tier}, character is tier {character_tier}",
        )

    def __str__(self):
        return f"Tier: >= {self.minimum_tier}"


# Character Unlocks


class CharacterUnlock(models.Model):
    """Records what class levels a character has unlocked."""

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="unlocks",
    )
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="character_unlocks",
    )
    target_level = models.PositiveIntegerField(
        help_text="Level unlocked for this class",
    )
    unlocked_date = models.DateTimeField(auto_now_add=True)
    xp_spent = models.PositiveIntegerField(
        default=0,
        help_text="XP actually spent on this unlock",
    )

    class Meta:
        unique_together = ["character", "character_class", "target_level"]
        ordering = ["-unlocked_date"]
        indexes = [models.Index(fields=["character", "-unlocked_date"])]

    def __str__(self):
        return (
            f"{self.character.key}: {self.character_class.name} Level "
            f"{self.target_level}"
        )
