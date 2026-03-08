"""
Achievements System Models

Tracks player accomplishments across all game systems. Other systems fire stat
increments into StatTracker; the achievements engine evaluates requirements
and awards achievements when thresholds are met.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.achievements.constants import ComparisonType, NotificationLevel, RewardType


class StatTracker(models.Model):
    """
    Tracks a single numeric stat for a character.

    Other game systems increment these counters (e.g., "quests_completed",
    "monsters_slain"). The achievements engine checks stat values against
    AchievementRequirement thresholds.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="stat_trackers",
        help_text="The character this stat belongs to",
    )
    stat_key = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Identifier for the tracked stat (e.g., 'quests_completed')",
    )
    value = models.IntegerField(
        default=0,
        help_text="Current value of the tracked stat",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this stat was last modified",
    )

    class Meta:
        unique_together = ["character_sheet", "stat_key"]

    def __str__(self) -> str:
        return f"{self.character_sheet} - {self.stat_key}: {self.value}"


class Achievement(SharedMemoryModel):
    """
    Definition of an achievement that characters can earn.

    Achievements are lookup data that rarely change. They can be chained
    via prerequisite (e.g., "Novice Explorer" -> "Seasoned Explorer").
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name of the achievement",
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="URL-safe identifier for the achievement",
    )
    description = models.TextField(
        help_text="What this achievement represents and how to earn it",
    )
    hidden = models.BooleanField(
        default=True,
        help_text="If true, achievement details are hidden until earned or discovered",
    )
    icon = models.CharField(
        max_length=200,
        blank=True,
        help_text="Icon identifier for frontend display",
    )
    notification_level = models.CharField(
        max_length=20,
        choices=NotificationLevel.choices,
        default=NotificationLevel.PERSONAL,
        help_text="Who gets notified when this achievement is earned",
    )
    prerequisite = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_in_chain",
        help_text="Achievement that must be earned before this one is available",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive achievements cannot be earned",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AchievementRequirement(models.Model):
    """
    A stat threshold that must be met for an achievement.

    An achievement may have multiple requirements, all of which must be
    satisfied for the achievement to be awarded.
    """

    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="requirements",
        help_text="The achievement this requirement belongs to",
    )
    stat_key = models.CharField(
        max_length=200,
        help_text="The stat key to check against (must match StatTracker.stat_key)",
    )
    threshold = models.IntegerField(
        help_text="The value to compare against",
    )
    comparison = models.CharField(
        max_length=10,
        choices=ComparisonType.choices,
        default=ComparisonType.GTE,
        help_text="How to compare the stat value to the threshold",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable description of this requirement",
    )

    class Meta:
        ordering = ["achievement", "id"]

    def __str__(self) -> str:
        return (
            f"{self.achievement.name}: {self.stat_key} "
            f"{self.get_comparison_display()} {self.threshold}"
        )


class Discovery(models.Model):
    """
    Records when a hidden achievement is first discovered by any character.

    Only one Discovery exists per achievement. Once discovered, the achievement
    becomes visible to all players.
    """

    achievement = models.OneToOneField(
        Achievement,
        on_delete=models.CASCADE,
        related_name="discovery",
        help_text="The achievement that was discovered",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this achievement was first discovered",
    )

    class Meta:
        verbose_name_plural = "discoveries"

    def __str__(self) -> str:
        return f"Discovery: {self.achievement.name}"


class CharacterAchievement(models.Model):
    """
    Records a character earning an achievement.

    Links a character to an achievement with timestamp and optional
    discovery credit.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="achievements",
        help_text="The character who earned this achievement",
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="character_achievements",
        help_text="The achievement that was earned",
    )
    earned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this achievement was earned",
    )
    discovery = models.ForeignKey(
        Discovery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discoverers",
        help_text="The discovery record if this character was among the first to find it",
    )

    class Meta:
        unique_together = ["character_sheet", "achievement"]

    def __str__(self) -> str:
        return f"{self.character_sheet} - {self.achievement.name}"


class AchievementReward(models.Model):
    """
    A reward granted when an achievement is earned.

    An achievement can have multiple rewards of different types.
    """

    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="rewards",
        help_text="The achievement that grants this reward",
    )
    reward_type = models.CharField(
        max_length=20,
        choices=RewardType.choices,
        help_text="The category of reward",
    )
    reward_key = models.CharField(
        max_length=200,
        help_text="Identifier for the specific reward (e.g., title slug, bonus key)",
    )
    reward_value = models.CharField(
        max_length=200,
        blank=True,
        help_text="Additional value data for the reward",
    )
    description = models.CharField(
        max_length=200,
        help_text="Human-readable description of the reward",
    )

    def __str__(self) -> str:
        return f"{self.achievement.name}: {self.get_reward_type_display()} - {self.description}"
