"""
Achievements System Models

Tracks player accomplishments across all game systems. Other systems fire stat
increments into StatTracker; the achievements engine evaluates requirements
and awards achievements when thresholds are met.
"""

from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.achievements.constants import (
    ComparisonType,
    ConditionEventType,
    NotificationLevel,
    RewardType,
)
from world.contributors.models import CreditedContent
from world.roster.models import RosterTenure

# String model reference for the CharacterSheet FK target. Using a single
# constant keeps the lazy "app_label.ModelName" reference consistent across the
# several models in this file that link to a character.
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"
# String model reference for the Persona FK target (#3466), matching
# `world/societies/models.py:46`.
PERSONA_MODEL = "arxii.Persona"


class StatDefinition(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Defines a trackable stat with display metadata.

    Normalizes stat keys so they can't get out of sync between
    StatTracker and AchievementStatRequirement. Staff-defined.
    """

    class NaturalKeyConfig:
        fields = ["key"]

    objects = NaturalKeyManager()

    key = models.CharField(
        max_length=200,
        unique=True,
        help_text="Dot-separated identifier (e.g., 'relationships.total_established')",
    )
    name = models.CharField(
        max_length=200,
        help_text="Player-facing display name",
    )
    description = models.TextField(
        blank=True,
        help_text="What this stat measures",
    )

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"


class StatTracker(SharedMemoryModel):
    """
    Tracks a single numeric stat for a character.

    Other game systems increment these counters (e.g., "quests_completed",
    "monsters_slain"). The achievements engine checks stat values against
    AchievementStatRequirement thresholds.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="stat_trackers",
        help_text="The character this stat belongs to",
    )
    stat = models.ForeignKey(
        StatDefinition,
        on_delete=models.CASCADE,
        related_name="trackers",
        help_text="The stat being tracked",
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
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "stat"],
                name="unique_character_stat",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} - {self.stat.key}: {self.value}"


class Achievement(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["slug"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_rewards(self) -> list["AchievementReward"]:
        """
        Get achievement rewards with related reward definitions loaded.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_rewards
        """
        return list(self.rewards.select_related("reward").all())


class DiscoverableContent(models.Model):
    """Abstract mixin: marks a content row as discoverable by attaching the
    Achievement (and global-first Discovery) earned the first time a character
    gains it. Inherited by gainable content models (ADR-0016); never a table
    of its own. Null = not discoverable."""

    discovery_achievement = models.ForeignKey(
        Achievement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Achievement granted (with global-first Discovery) the first time a "
        "character gains this content. Null = not discoverable.",
    )

    class Meta:
        abstract = True


class AchievementStatRequirement(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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
    stat = models.ForeignKey(
        StatDefinition,
        on_delete=models.CASCADE,
        related_name="requirements",
        help_text="The stat to check against",
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["achievement", "stat", "threshold", "comparison"]
        dependencies = ["arxii.Achievement", "arxii.StatDefinition"]

    class Meta:
        ordering = ["achievement", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["achievement", "stat", "threshold", "comparison"],
                name="unique_achievement_requirement",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.achievement.name}: {self.stat.key} "
            f"{self.get_comparison_display()} {self.threshold}"
        )

    def is_met(self, value: int) -> bool:
        """Return True if the given value satisfies this requirement's comparison."""
        if self.comparison == ComparisonType.GTE:
            return value >= self.threshold
        if self.comparison == ComparisonType.EQ:
            return value == self.threshold
        if self.comparison == ComparisonType.LTE:
            return value <= self.threshold
        return False


class Discovery(SharedMemoryModel):
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
    discovered_by_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.PROTECT,
        related_name="discoveries",
        help_text="The tenure (character piloted by a player) that first discovered "
        "this achievement. Required: discoveries are partly-OOC accolades earned "
        "through a character, and a sheet with no player tenure cannot claim a "
        "first-ever slot (#3055). Tenures are never deleted post-release, so this "
        "is PROTECT rather than CASCADE/SET_NULL.",
    )
    shared_with_tenures = models.ManyToManyField(
        RosterTenure,
        blank=True,
        related_name="shared_discoveries",
        help_text="Tenures that co-discovered this achievement in the same moment as "
        "the primary discoverer (a party or covenant finding it together). A "
        "player's full discovery record is the union of their tenures' "
        "'discoveries' (primary) and 'shared_discoveries' (shared credit) (#3055).",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this achievement was first discovered",
    )

    class Meta:
        verbose_name_plural = "discoveries"

    def __str__(self) -> str:
        return f"Discovery: {self.achievement.name}"

    @cached_property
    def cached_shared_tenures(self) -> list["RosterTenure"]:
        """Co-discoverer tenures (excluding the primary discoverer).

        This cached_property serves as the target for Prefetch(..., to_attr=). When
        prefetched, Django populates this directly. When accessed without prefetch,
        falls back to a fresh query. See Achievement.cached_rewards for the pattern.

        To invalidate: del instance.cached_shared_tenures
        """
        return list(self.shared_with_tenures.all())


class CharacterAchievement(SharedMemoryModel):
    """
    Records a character earning an achievement.

    Links a character to an achievement with timestamp and the earning tenure.
    Discovery credit (see ``is_discoverer``) derives from comparing that tenure
    against the achievement's Discovery record — not a stored FK (#3055).
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
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
    earned_by_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.PROTECT,
        related_name="earned_achievements",
        help_text="The tenure (character piloted by a player) that earned this achievement "
        "(#3055). Stamped from the sheet's current tenure inside grant_achievement — the "
        "same eligibility gate (can_earn_achievements) that already guarantees one exists. "
        "Required: an achievement is an acquisition-provenance record, and every co-earner "
        "of a party grant gets their own individually durable (player, character) pairing, "
        "not just the primary Discovery slot's discoverer. PROTECT: tenures are never "
        "deleted post-release (mirrors Discovery.discovered_by_tenure, #3060).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "achievement"],
                name="unique_character_achievement",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} - {self.achievement.name}"

    def is_discoverer(self) -> bool:
        """Whether this row's earning tenure was a primary or shared co-discoverer.

        Derives entirely from tenure records (#3055) — the discovery FK this used to
        read (`CharacterAchievement.discovery`) is gone; tenure records are the single
        discovery-credit mechanism. Compares `earned_by_tenure` against the
        achievement's `Discovery.discovered_by_tenure` (primary) and
        `shared_with_tenures` (shared). Callers that need N+1 safety across many rows
        should select_related `achievement__discovery` and prefetch
        `achievement__discovery__shared_with_tenures` (see
        `CharacterAchievementViewSet.get_queryset`).
        """
        try:
            discovery = self.achievement.discovery
        except Discovery.DoesNotExist:
            return False
        if discovery.discovered_by_tenure_id == self.earned_by_tenure_id:
            return True
        shared_ids = {tenure.id for tenure in discovery.cached_shared_tenures}
        return self.earned_by_tenure_id in shared_ids


class RewardDefinition(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Defines a reward that can be granted by achievements.

    Normalizes reward identifiers so they can't get out of sync across
    the codebase. Staff-defined. As game systems are built, these will
    be filled in with references to titles, bonuses, cosmetics, etc.
    """

    key = models.CharField(
        max_length=200,
        unique=True,
        help_text="Dot-separated identifier (e.g., 'title.champion', 'cosmetic.golden_border')",
    )
    name = models.CharField(
        max_length=200,
        help_text="Player-facing display name",
    )
    reward_type = models.CharField(
        max_length=20,
        choices=RewardType.choices,
        help_text="The category of reward",
    )
    description = models.TextField(
        blank=True,
        help_text="What this reward is",
    )
    modifier_target = models.ForeignKey(
        "arxii.ModifierTarget",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reward_definitions",
        help_text=(
            "For BONUS rewards: which stat the bonus modifies (e.g. allure). The amount comes "
            "from AchievementReward.reward_value."
        ),
    )
    distinction = models.ForeignKey(
        "arxii.Distinction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reward_definitions",
        help_text=(
            "For DISTINCTION rewards: which Distinction to grant/rank-up (#2037). The optional "
            "explicit rank comes from AchievementReward.reward_value."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    class Meta:
        ordering = ["reward_type", "key"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"


class AchievementReward(NaturalKeyMixin, SharedMemoryModel):
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
    reward = models.ForeignKey(
        RewardDefinition,
        on_delete=models.CASCADE,
        related_name="achievement_rewards",
        help_text="The reward definition to grant",
    )
    reward_value = models.CharField(
        max_length=200,
        blank=True,
        help_text="Additional value data for the reward (e.g., bonus amount)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["achievement", "reward"]
        dependencies = ["arxii.Achievement", "arxii.RewardDefinition"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["achievement", "reward"],
                name="unique_achievement_reward",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.achievement.name}: {self.reward.name}"


class ConditionStatRule(NaturalKeyMixin, SharedMemoryModel):
    """Rule mapping a ConditionTemplate event to a StatDefinition increment.

    When the named event occurs to an instance of `condition` on a character,
    `stat` is incremented by `increment_amount` for that character. The
    achievements engine then evaluates requirements via the existing
    StatHandler.increment pipeline.

    Lives in achievements/ because achievements own the rule set; conditions
    know nothing about this table. Decoupling per the bridge-table pattern:
    producer (conditions) is unaware of consumer (achievements) concerns.
    """

    stat = models.ForeignKey(
        StatDefinition,
        on_delete=models.CASCADE,
        related_name="condition_rules",
    )
    condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="stat_rules_for",
    )
    event_type = models.CharField(
        max_length=32,
        choices=ConditionEventType.choices,
    )
    increment_amount = models.PositiveIntegerField(default=1)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["stat", "condition", "event_type"]
        dependencies = ["arxii.StatDefinition", "arxii.ConditionTemplate"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stat", "condition", "event_type"],
                name="unique_condition_stat_rule",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.condition.name} {self.event_type} → {self.stat.key}"


class PersonaTitle(SharedMemoryModel):
    """A title a persona has earned and may display (#1522, retargeted #3466).

    Hangs on the **Persona**, not the CharacterSheet: a title is how the world names a
    face, and the legend system it draws from is persona-scoped throughout. This is also
    what makes an honor safe - a deed earned behind a mask titles the mask, and can never
    surface on the character sheet and out the player.

    Exactly one of ``reward`` (an authored achievement title) or ``legend_entry`` (a deed
    that crossed its station's threshold) is set.
    """

    persona = models.ForeignKey(PERSONA_MODEL, on_delete=models.CASCADE, related_name="titles")
    reward = models.ForeignKey(
        RewardDefinition,
        on_delete=models.CASCADE,
        related_name="persona_titles",
        null=True,
        blank=True,
        help_text="The TITLE-type RewardDefinition this title comes from.",
    )
    legend_entry = models.ForeignKey(
        "arxii.LegendEntry",
        on_delete=models.CASCADE,
        related_name="titles",
        null=True,
        blank=True,
        help_text="The deed whose name this title is (#3466).",
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["persona", "reward", "legend_entry"]
        constraints = [
            models.CheckConstraint(
                condition=Q(reward__isnull=False, legend_entry__isnull=True)
                | Q(reward__isnull=True, legend_entry__isnull=False),
                name="personatitle_exactly_one_source",
            ),
            models.UniqueConstraint(
                fields=["persona", "reward"],
                name="unique_persona_reward_title",
                condition=Q(reward__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["persona", "legend_entry"],
                name="unique_persona_deed_title",
                condition=Q(legend_entry__isnull=False),
            ),
        ]

    @property
    def display_name(self) -> str:
        """The player-facing name, from whichever branch is set."""
        return self.reward.name if self.reward_id else self.legend_entry.title

    def __str__(self) -> str:
        return f"{self.persona}: {self.display_name}"
