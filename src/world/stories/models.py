from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    EraStatus,
    StoryMilestoneType,
    StoryScope,
    TransitionMode,
)
from world.stories.types import (
    ConnectionType,
    ParticipationLevel,
    StoryPrivacy,
    StoryStatus,
    TrustLevel,
)

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser


class TrustCategory(SharedMemoryModel):
    """
    Flexible trust categories that can be defined dynamically.
    Each category represents something a player might need to be trusted to handle well.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=("Short name for the trust category (e.g., 'antagonism', 'mature_themes')"),
    )
    display_name = models.CharField(
        max_length=200,
        help_text=("Human-readable display name (e.g., 'Antagonistic Roleplay')"),
    )
    description = models.TextField(
        help_text=("Description of what this trust category covers and why trust is needed"),
    )

    # Organizational fields
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this category is currently in use",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Account that created this trust category",
    )

    class Meta:
        verbose_name_plural = "Trust Categories"

    def __str__(self) -> str:
        return self.display_name


class Story(SharedMemoryModel):
    """
    Core story model representing missions/quests/narrative arcs.
    Stories are the primary gameplay mechanism in Arx II.
    """

    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=StoryStatus.choices,
        default=StoryStatus.INACTIVE,
    )
    privacy = models.CharField(
        max_length=20,
        choices=StoryPrivacy.choices,
        default=StoryPrivacy.PUBLIC,
    )
    scope = models.CharField(
        max_length=20,
        choices=StoryScope.choices,
        default=StoryScope.CHARACTER,
        help_text=(
            "Whether this story belongs to one character (CHARACTER), "
            "a covenant/group (GROUP), or the whole metaplot (GLOBAL)."
        ),
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="character_stories",
        help_text="For CHARACTER-scope stories: the character whose story this is.",
    )
    created_in_era = models.ForeignKey(
        "stories.Era",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stories_created_in_era",
        help_text="The metaplot era in which this story was created. Null = pre-era or ungrouped.",
    )

    # Ownership and management
    owners = models.ManyToManyField(
        "accounts.AccountDB",
        related_name="owned_stories",
        help_text="Players who own and can manage this story",
    )
    active_gms = models.ManyToManyField(
        "gm.GMProfile",
        related_name="active_stories",
        help_text="GM profiles currently running this story",
    )
    primary_table = models.ForeignKey(
        "gm.GMTable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_stories",
        help_text=(
            "Table bearing primary responsibility for this story. "
            "Individual beats/episodes may happen at other tables. "
            "Null = orphaned (no active oversight)."
        ),
    )

    # Trust requirements - stories can require trust in specific categories
    required_trust_categories = models.ManyToManyField(
        TrustCategory,
        through="StoryTrustRequirement",
        blank=True,
        help_text="Trust categories required to participate in this story",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "stories"

    def __str__(self) -> str:
        return self.title

    def is_active(self) -> bool:
        """Check if story has active GMs and is not inactive/completed/cancelled"""
        active_gms = cast(Any, self.active_gms)
        return self.status == StoryStatus.ACTIVE and active_gms.exists()

    def can_player_apply(self, account: "AbstractBaseUser") -> bool:
        """Check if a player can apply to participate in this story"""
        if self.privacy == StoryPrivacy.PRIVATE:
            return False

        # Check trust requirements
        try:
            trust_profile = cast(Any, account).trust_profile
            # Get all trust requirements for this story
            requirements = cast(Any, self).trust_requirements.all()
            for req in requirements:
                current_level = trust_profile.get_trust_level_for_category(
                    req.trust_category,
                )
                if current_level < req.minimum_trust_level:
                    return False
            return True
        except ObjectDoesNotExist:
            # No trust profile means no trust granted
            return len(cast(Any, self).trust_requirements.all()) == 0

    def get_trust_requirements_summary(self) -> list[dict[str, str]]:
        """Get a summary of trust requirements for display"""
        return [
            {
                "category": req.trust_category.display_name,
                "minimum_level": req.get_minimum_trust_level_display(),
            }
            for req in cast(Any, self).trust_requirements.all()
        ]


class StoryTrustRequirement(SharedMemoryModel):
    """
    Through model for Story trust requirements.
    Allows specifying minimum trust level needed for each category.
    """

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="trust_requirements",
    )
    trust_category = models.ForeignKey(TrustCategory, on_delete=models.CASCADE)
    minimum_trust_level = models.IntegerField(
        choices=TrustLevel.choices,
        default=TrustLevel.BASIC,
        help_text="Minimum trust level required for this category",
    )

    # Optional metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Who added this requirement",
    )
    notes = models.TextField(
        blank=True,
        help_text="Why this trust requirement was added",
    )

    class Meta:
        unique_together = ["story", "trust_category"]

    def __str__(self) -> str:
        story = cast(Any, self.story)
        trust_category = cast(Any, self.trust_category)
        return (
            f"{story.title}: {trust_category.display_name} "
            f"({cast(Any, self).get_minimum_trust_level_display()})"
        )


class StoryParticipation(SharedMemoryModel):
    """Tracks character participation in stories with trust and permission levels"""

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="story_participations",
    )
    participation_level = models.CharField(
        max_length=20,
        choices=ParticipationLevel.choices,
        default=ParticipationLevel.OPTIONAL,
    )

    # Trust and permissions
    trusted_by_owner = models.BooleanField(
        default=False,
        help_text="Story owner has explicitly trusted this player for this story",
    )

    # Participation tracking
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["story", "character"]

    def __str__(self) -> str:
        return f"{self.character} in {self.story}"


class Chapter(SharedMemoryModel):
    """Major story divisions containing multiple episodes"""

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="chapters")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField()

    # Chapter progression
    is_active = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Narrative tracking
    summary = models.TextField(
        blank=True,
        help_text="Summary of what happened in this chapter",
    )
    consequences = models.TextField(
        blank=True,
        help_text="Key consequences that affect future chapters",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["story", "order"]
        ordering = ["story", "order"]

    def __str__(self) -> str:
        story = cast(Any, self.story)
        return f"{story.title} - Chapter {self.order}: {self.title}"


class Episode(SharedMemoryModel):
    """Story episodes containing a small number of connected scenes"""

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        related_name="episodes",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField()

    # Episode status
    is_active = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Narrative connection tracking
    summary = models.TextField(
        blank=True,
        help_text="Summary of this episode's plot beats",
    )
    consequences = models.TextField(
        blank=True,
        help_text="What consequences lead to the next episode",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["chapter", "order"]
        ordering = ["chapter", "order"]

    def __str__(self) -> str:
        chapter = cast(Any, self.chapter)
        return f"{chapter.story.title} - Ep {self.order}: {self.title}"


class EpisodeScene(SharedMemoryModel):
    """Links scenes to episodes, allowing scenes to update multiple stories"""

    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name="episode_scenes",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="story_episodes",
    )
    order = models.PositiveIntegerField()

    class Meta:
        unique_together = ["episode", "scene"]
        ordering = ["episode", "order"]

    def __str__(self) -> str:
        return f"{self.episode} - Scene {self.order}"


class PlayerTrust(SharedMemoryModel):
    """
    Aggregate trust profile for a player.
    This is a lightweight model that helps with queries and caching.
    """

    account = models.OneToOneField(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="trust_profile",
    )

    # Trust categories are linked via PlayerTrustLevel through model
    trust_categories = models.ManyToManyField(
        TrustCategory,
        through="PlayerTrustLevel",
        blank=True,
        help_text="Trust categories and levels for this player",
    )

    # GM trust is special and universal
    gm_trust_level = models.IntegerField(
        choices=TrustLevel.choices,
        default=TrustLevel.UNTRUSTED,
        help_text="General GM trust level, not category-specific",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        account = cast(Any, self.account)
        return f"Trust Profile: {account.username}"

    @property
    def total_positive_feedback(self) -> int:
        """Aggregate positive feedback count from all trust levels"""
        trust_levels = cast(Any, self).trust_levels.all()
        return sum(level.positive_feedback_count for level in trust_levels)

    @property
    def total_negative_feedback(self) -> int:
        """Aggregate negative feedback count from all trust levels"""
        trust_levels = cast(Any, self).trust_levels.all()
        return sum(level.negative_feedback_count for level in trust_levels)

    def get_trust_level_for_category(self, trust_category: TrustCategory) -> int:
        """Get trust level for a specific trust category"""
        try:
            trust_level = cast(Any, self).trust_levels.get(trust_category=trust_category)
            return cast(int, trust_level.trust_level)
        except PlayerTrustLevel.DoesNotExist:
            return cast(int, TrustLevel.UNTRUSTED)

    def get_trust_level_for_category_name(self, category_name: str) -> int:
        """Get trust level for a trust category by name"""
        try:
            trust_category = cast(Any, TrustCategory).objects.get(name=category_name)
            return self.get_trust_level_for_category(trust_category)
        except TrustCategory.DoesNotExist:
            return cast(int, TrustLevel.UNTRUSTED)

    def has_minimum_trust_for_categories(self, required_categories: list) -> bool:
        """Check if player has minimum required trust for all categories"""
        for category_req in required_categories:
            if isinstance(category_req, dict):
                category_name = category_req.get("category")
                min_level = category_req.get("minimum_level", TrustLevel.BASIC)
            else:
                # Assume it's just a category name requiring basic trust
                category_name = str(category_req)
                min_level = TrustLevel.BASIC

            if category_name:  # Only process if category_name is not None
                current_level = self.get_trust_level_for_category_name(category_name)
                if current_level < min_level:
                    return False

        return True


class PlayerTrustLevel(SharedMemoryModel):
    """
    Individual trust level for a player in a specific trust category.
    This is the bridge table between PlayerTrust and TrustCategory with additional data.
    """

    player_trust = models.ForeignKey(
        PlayerTrust,
        on_delete=models.CASCADE,
        related_name="trust_levels",
    )
    trust_category = models.ForeignKey(
        TrustCategory,
        on_delete=models.CASCADE,
        related_name="player_trust_levels",
    )
    trust_level = models.IntegerField(
        choices=TrustLevel.choices,
        default=TrustLevel.UNTRUSTED,
    )

    # Trust score tracking (negative feedback hurts more than positive helps)
    positive_feedback_count = models.PositiveIntegerField(default=0)
    negative_feedback_count = models.PositiveIntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(
        blank=True,
        help_text="Notes about why this trust level was granted or revoked",
    )

    class Meta:
        unique_together = ["player_trust", "trust_category"]

    def __str__(self) -> str:
        return (
            f"{cast(Any, self.player_trust).account.username}: "
            f"{cast(Any, self.trust_category).display_name} "
            f"({cast(Any, self).get_trust_level_display()})"
        )


class StoryFeedback(SharedMemoryModel):
    """Feedback on story participation for trust building"""

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="feedback")
    reviewer = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="given_feedback",
    )
    reviewed_player = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="received_feedback",
    )

    # Feedback details
    trust_categories = models.ManyToManyField(
        TrustCategory,
        through="TrustCategoryFeedbackRating",
        blank=True,
        help_text="Trust categories this feedback applies to with ratings",
    )
    is_gm_feedback = models.BooleanField(
        default=False,
        help_text="True if feedback is about GM performance",
    )

    comments = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["story", "reviewer", "reviewed_player"]

    def __str__(self) -> str:
        reviewed_player = cast(Any, self.reviewed_player)
        story = cast(Any, self.story)
        return f"Feedback for {reviewed_player.username} in {story.title}"

    def get_average_rating(self) -> float:
        """Get average rating across all trust categories"""
        ratings = cast(Any, self).category_ratings.all()
        if not ratings:
            return 0
        return sum(rating.rating for rating in ratings) / len(ratings)

    def is_overall_positive(self) -> bool:
        """Check if overall feedback is positive (average rating > 0)"""
        return self.get_average_rating() > 0


class TrustCategoryFeedbackRating(SharedMemoryModel):
    """
    Through model for StoryFeedback trust categories with ratings.
    Allows rating performance in specific trust categories on a numerical scale.
    """

    feedback = models.ForeignKey(
        StoryFeedback,
        on_delete=models.CASCADE,
        related_name="category_ratings",
    )
    trust_category = models.ForeignKey(TrustCategory, on_delete=models.CASCADE)
    rating = models.IntegerField(
        choices=[
            (-2, "Very Poor"),
            (-1, "Poor"),
            (0, "Neutral/No Opinion"),
            (1, "Good"),
            (2, "Excellent"),
        ],
        help_text="Rating for how well this player handled this trust category",
    )
    notes = models.TextField(
        blank=True,
        help_text="Specific notes about performance in this category",
    )

    class Meta:
        unique_together = ["feedback", "trust_category"]

    def __str__(self) -> str:
        return (
            f"{cast(Any, self.feedback).reviewed_player.username} - "
            f"{cast(Any, self.trust_category).display_name}: "
            f"{cast(Any, self).get_rating_display()}"
        )


class EraManager(models.Manager):
    def get_active(self) -> "Era | None":
        """Return the currently ACTIVE Era, or None if none is active."""
        return self.filter(status=EraStatus.ACTIVE).first()


class Era(SharedMemoryModel):
    """Staff-activated metaplot era ('Season' in player-facing UI)."""

    objects = EraManager()

    name = models.SlugField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    season_number = models.PositiveIntegerField(help_text="Player-facing 'Season N' number.")
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=EraStatus.choices,
        default=EraStatus.UPCOMING,
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    concluded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status=EraStatus.ACTIVE),
                name="only_one_active_era",
            )
        ]

    def __str__(self) -> str:
        return f"Season {self.season_number}: {self.display_name}"


class Transition(SharedMemoryModel):
    """A guarded edge from one Episode to another."""

    source_episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="outbound_transitions",
    )
    target_episode = models.ForeignKey(
        "stories.Episode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_transitions",
        help_text="May be null when next episode is unauthored (frontier pause).",
    )
    mode = models.CharField(
        max_length=20,
        choices=TransitionMode.choices,
        default=TransitionMode.AUTO,
        help_text=(
            "AUTO fires when eligibility is satisfied. GM_CHOICE requires a Lead "
            "GM to pick from the eligible set."
        ),
    )
    connection_type = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        blank=True,
        default="",
        help_text="Narrative flavor: THEREFORE / BUT.",
    )
    connection_summary = models.TextField(
        blank=True,
        help_text="Short narrative description of why this transition fires.",
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_episode", "order"]
        indexes = [
            models.Index(fields=["source_episode"]),
        ]

    def __str__(self) -> str:
        target_name = self.target_episode.title if self.target_episode else "(unauthored)"
        return f"{self.source_episode.title} -> {target_name}"

    @cached_property
    def cached_required_outcomes(self) -> list["TransitionRequiredOutcome"]:
        """Routing requirements for this transition with beat pre-fetched.

        Serves as the ``to_attr`` target for::

            Prefetch(
                "required_outcomes",
                queryset=TransitionRequiredOutcome.objects.select_related("beat"),
                to_attr="cached_required_outcomes",
            )

        When not prefetched, falls back to a fresh query.

        To invalidate: ``del transition.cached_required_outcomes``.
        """
        return list(self.required_outcomes.select_related("beat").all())


class Beat(SharedMemoryModel):
    """
    A boolean predicate attached to an episode, with rich outcome state.

    Predicate-type-specific config is stored as nullable columns on this model.
    ``clean()`` enforces that exactly the right columns are populated for the
    chosen predicate_type.
    """

    episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="beats",
    )
    predicate_type = models.CharField(
        max_length=40,
        choices=BeatPredicateType.choices,
        default=BeatPredicateType.GM_MARKED,
    )
    outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
        default=BeatOutcome.UNSATISFIED,
        help_text=(
            "The story's current outcome on this beat — a single shared value across "
            "the story's progression (the owning character for CHARACTER scope, the "
            "group for GROUP scope, the world for GLOBAL scope). A story has exactly "
            "one progression trail, so this field represents the whole story's state, "
            "not per-character state. Historical per-character contributions live in "
            "BeatCompletion."
        ),
    )
    visibility = models.CharField(
        max_length=20,
        choices=BeatVisibility.choices,
        default=BeatVisibility.HINTED,
    )

    # Text layers
    internal_description = models.TextField(
        help_text="Author/Lead GM/staff view: real predicate + meaning.",
    )
    player_hint = models.TextField(
        blank=True,
        help_text="Shown while active (if visibility=HINTED or VISIBLE).",
    )
    player_resolution_text = models.TextField(
        blank=True,
        help_text="Shown in story log after beat completes.",
    )

    # Predicate-type-specific config (nullable; populated based on predicate_type)
    required_level = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For CHARACTER_LEVEL_AT_LEAST predicates.",
    )
    required_achievement = models.ForeignKey(
        "achievements.Achievement",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For ACHIEVEMENT_HELD predicates.",
    )
    required_condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For CONDITION_HELD predicates.",
    )
    required_codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For CODEX_ENTRY_UNLOCKED predicates.",
    )
    referenced_story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="referenced_by_beats",
        help_text="For STORY_AT_MILESTONE predicates.",
    )
    referenced_milestone_type = models.CharField(
        max_length=30,
        choices=StoryMilestoneType.choices,
        blank=True,
        default="",
        help_text="Which kind of milestone to check on referenced_story.",
    )
    referenced_chapter = models.ForeignKey(
        "stories.Chapter",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For referenced_milestone_type=CHAPTER_REACHED.",
    )
    referenced_episode = models.ForeignKey(
        "stories.Episode",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For referenced_milestone_type=EPISODE_REACHED.",
    )
    required_points = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For AGGREGATE_THRESHOLD predicates — total contribution points required.",
    )

    # AGM eligibility flag — Lead GM may expose specific beats to AGM pool.
    agm_eligible = models.BooleanField(
        default=False,
        help_text="Lead GM may flag this beat to be claimable by Assistant GMs.",
    )

    # Scaffolding for future phases (not wired yet):
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional wall-clock deadline. Expiry handling deferred to Phase 3+.",
    )

    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["episode", "order"]
        indexes = [
            models.Index(fields=["episode", "outcome"]),
        ]

    # Invariant mapping: predicate_type -> required config field names.
    # For STORY_AT_MILESTONE, use _required_config_fields() which is milestone-type-aware.
    _REQUIRED_CONFIG: dict[str, tuple[str, ...]] = {
        BeatPredicateType.GM_MARKED: (),
        BeatPredicateType.CHARACTER_LEVEL_AT_LEAST: ("required_level",),
        BeatPredicateType.ACHIEVEMENT_HELD: ("required_achievement",),
        BeatPredicateType.CONDITION_HELD: ("required_condition_template",),
        BeatPredicateType.CODEX_ENTRY_UNLOCKED: ("required_codex_entry",),
        BeatPredicateType.AGGREGATE_THRESHOLD: ("required_points",),
    }

    def _required_config_fields(self) -> tuple[str, ...]:
        """Return the set of config fields required for this beat's predicate_type.

        For STORY_AT_MILESTONE, the required fields depend on referenced_milestone_type.
        All other types delegate to _REQUIRED_CONFIG.
        """
        if self.predicate_type == BeatPredicateType.STORY_AT_MILESTONE:
            base: tuple[str, ...] = ("referenced_story", "referenced_milestone_type")
            if self.referenced_milestone_type == StoryMilestoneType.CHAPTER_REACHED:
                return (*base, "referenced_chapter")
            if self.referenced_milestone_type == StoryMilestoneType.EPISODE_REACHED:
                return (*base, "referenced_episode")
            # STORY_RESOLVED needs only the story reference.
            return base
        return self._REQUIRED_CONFIG.get(self.predicate_type, ())

    def clean(self) -> None:
        super().clean()
        required = self._required_config_fields()
        errors: dict[str, str] = {}
        for field_name in required:
            if getattr(self, field_name) in (None, ""):
                errors[field_name] = f"Required when predicate_type is {self.predicate_type}."
        # All non-required config fields must be null for this predicate_type.
        all_config_fields = {
            "required_level",
            "required_achievement",
            "required_condition_template",
            "required_codex_entry",
            "referenced_story",
            "referenced_milestone_type",
            "referenced_chapter",
            "referenced_episode",
            "required_points",
        }
        for field_name in all_config_fields - set(required):
            val = getattr(self, field_name)
            if val is not None and val != "":
                errors[field_name] = f"Must be null when predicate_type is {self.predicate_type}."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Beat({self.predicate_type}) on {self.episode.title}"


class EpisodeProgressionRequirement(SharedMemoryModel):
    """A beat that must reach ``required_outcome`` before any outbound transition fires."""

    episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="progression_requirements",
    )
    beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.CASCADE,
        related_name="gating_for_episodes",
    )
    required_outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
        default=BeatOutcome.SUCCESS,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["episode", "beat"],
                name="unique_progression_req_per_episode_beat",
            )
        ]

    def __str__(self) -> str:
        return f"{self.episode.title} requires beat #{self.beat_id} = {self.required_outcome}"


class TransitionRequiredOutcome(SharedMemoryModel):
    """A beat outcome that must be satisfied for this transition to be eligible."""

    transition = models.ForeignKey(
        "stories.Transition",
        on_delete=models.CASCADE,
        related_name="required_outcomes",
    )
    beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.CASCADE,
        related_name="routing_for_transitions",
    )
    required_outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transition", "beat"],
                name="unique_routing_req_per_transition_beat",
            )
        ]

    def __str__(self) -> str:
        return (
            f"Transition #{self.transition_id} requires beat #{self.beat_id}"
            f" = {self.required_outcome}"
        )


class AggregateBeatContributionManager(models.Manager):
    def total_for_beat(self, beat: "Beat") -> int:
        """Sum contributions for a beat; returns 0 when no rows exist."""
        return self.filter(beat=beat).aggregate(total=models.Sum("points"))["total"] or 0


class AggregateBeatContribution(SharedMemoryModel):
    """Per-character contribution toward an AGGREGATE_THRESHOLD beat.

    Different gameplay events (siege battle won, research mission completed,
    etc.) produce contributions; the beat flips to SUCCESS when total
    contributions cross the beat's required_points threshold.

    Each row records the character, their current roster tenure (audit
    trail), the era active at contribution time, the points, and a brief
    source note explaining what the contribution was for.
    """

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="aggregate_contributions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="aggregate_contributions",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=(
            "Which roster tenure was active when this contribution was made. For audit only."
        ),
    )
    points = models.PositiveIntegerField(
        help_text="Contribution points toward the beat's required_points threshold.",
    )
    era = models.ForeignKey(
        Era,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="aggregate_contributions",
    )
    source_note = models.TextField(
        blank=True,
        help_text=(
            "Brief description of what produced this contribution (siege battle, mission, etc.)."
        ),
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = AggregateBeatContributionManager()

    class Meta:
        indexes = [
            models.Index(fields=["beat", "character_sheet"]),
            models.Index(fields=["beat", "-recorded_at"]),
            models.Index(fields=["character_sheet", "-recorded_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"AggregateBeatContribution(beat=#{self.beat_id},"
            f" char=#{self.character_sheet_id}, points={self.points})"
        )


class BeatCompletion(SharedMemoryModel):
    """Audit ledger row for each beat outcome applied to a character's progress."""

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="beat_completions",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=(
            "Which roster tenure (which player) was active when this beat "
            "completed. For audit only."
        ),
    )
    outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
    )
    era = models.ForeignKey(
        Era,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="beat_completions",
    )
    gm_notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["beat", "character_sheet"]),
            models.Index(fields=["character_sheet", "-recorded_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"BeatCompletion(beat=#{self.beat_id}, char=#{self.character_sheet_id},"
            f" outcome={self.outcome})"
        )


class EpisodeResolution(SharedMemoryModel):
    """Audit record when an episode is resolved and (optionally) a transition fires.

    Exactly one of character_sheet / gm_table / neither must be populated,
    matching the story's scope:
      - CHARACTER scope → character_sheet non-null, gm_table null.
      - GROUP scope     → gm_table non-null, character_sheet null.
      - GLOBAL scope    → both null (the story itself is the identifier).
    """

    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name="resolutions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="episode_resolutions",
        help_text="For CHARACTER-scope stories: the character whose progress advanced.",
    )
    gm_table = models.ForeignKey(
        "gm.GMTable",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="episode_resolutions",
        help_text="For GROUP-scope stories: the GMTable whose progress advanced.",
    )
    chosen_transition = models.ForeignKey(
        Transition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolutions_using",
        help_text="Null when the episode resolves with no transition (frontier pause).",
    )
    resolved_by = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="episode_resolutions",
    )
    era = models.ForeignKey(
        Era,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="episode_resolutions",
    )
    gm_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["episode", "-resolved_at"]),
            models.Index(fields=["character_sheet", "-resolved_at"]),
            models.Index(fields=["gm_table", "-resolved_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        scope = self.episode.chapter.story.scope
        if scope == StoryScope.CHARACTER and not self.character_sheet_id:
            raise ValidationError({"character_sheet": "Required for CHARACTER-scope stories."})
        if scope == StoryScope.GROUP and not self.gm_table_id:
            raise ValidationError({"gm_table": "Required for GROUP-scope stories."})
        if scope == StoryScope.CHARACTER and self.gm_table_id:
            raise ValidationError({"gm_table": "Must be null for CHARACTER-scope stories."})
        if scope == StoryScope.GROUP and self.character_sheet_id:
            raise ValidationError({"character_sheet": "Must be null for GROUP-scope stories."})
        if scope == StoryScope.GLOBAL and (self.character_sheet_id or self.gm_table_id):
            msg = "Both character_sheet and gm_table must be null for GLOBAL-scope stories."
            raise ValidationError(msg)

    def __str__(self) -> str:
        if self.chosen_transition and self.chosen_transition.target_episode:
            dest = self.chosen_transition.target_episode.title
        else:
            dest = "(frontier)"
        return f"EpisodeResolution({self.episode.title} -> {dest})"


class GroupStoryProgress(SharedMemoryModel):
    """Per-group pointer into a GROUP-scope story's current state.

    One row per story — the entire GMTable shares the progression trail.
    Group members never diverge onto separate branches; the group resolves
    episodes as a unit.

    For individual character contributions within a group story, see
    AggregateBeatContribution (Phase 2 Wave 4) and BeatCompletion.
    """

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="group_progress_records",
    )
    gm_table = models.ForeignKey(
        "gm.GMTable",
        on_delete=models.CASCADE,
        related_name="story_progress",
    )
    current_episode = models.ForeignKey(
        Episode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_group_progress_records",
        help_text="Null while the story is at the frontier (unauthored) or before start.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "gm_table"],
                name="unique_group_progress_per_story_per_table",
            )
        ]
        indexes = [
            models.Index(fields=["gm_table", "is_active"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.story_id and self.story.scope != StoryScope.GROUP:
            raise ValidationError({"story": "GroupStoryProgress requires a GROUP-scope story."})

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        ep = self.current_episode.title if self.current_episode else "(frontier)"
        return f"GroupStoryProgress({self.gm_table.name} in {self.story.title} @ {ep})"


class GlobalStoryProgress(SharedMemoryModel):
    """Singleton pointer into a GLOBAL-scope story's current state.

    One row per story — the whole server shares the progression trail for
    the metaplot. Characters opt-in/out via StoryParticipation, but the
    progression itself is a single thread. OneToOne on story enforces
    the singleton invariant at the DB level.
    """

    story = models.OneToOneField(
        Story,
        on_delete=models.CASCADE,
        related_name="global_progress",
    )
    current_episode = models.ForeignKey(
        Episode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_global_progress_records",
        help_text="Null while the story is at the frontier or before start.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.story_id and self.story.scope != StoryScope.GLOBAL:
            raise ValidationError({"story": "GlobalStoryProgress requires a GLOBAL-scope story."})

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        ep = self.current_episode.title if self.current_episode else "(frontier)"
        return f"GlobalStoryProgress({self.story.title} @ {ep})"


class StoryProgress(SharedMemoryModel):
    """Per-character pointer into a CHARACTER-scope story's current state."""

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="story_progress",
    )
    current_episode = models.ForeignKey(
        Episode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_progress_records",
        help_text="Null while the story is at the frontier (unauthored) or before start.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "character_sheet"],
                name="unique_progress_per_story_per_character",
            )
        ]
        indexes = [
            models.Index(fields=["character_sheet", "is_active"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.story.scope == StoryScope.CHARACTER:
            if self.story.character_sheet_id is None:
                # Story has no owner wired — cannot validate. Allow; service layer will flag.
                return
            if self.character_sheet_id != self.story.character_sheet_id:
                raise ValidationError(
                    {
                        "character_sheet": (
                            "StoryProgress for a CHARACTER-scope story must belong to the "
                            "story's owning character_sheet."
                        )
                    }
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        episode_title = self.current_episode.title if self.current_episode else "(frontier)"
        char_label = self.character_sheet.character.db_key if self.character_sheet_id else "?"
        return f"StoryProgress({char_label} in {self.story.title} @ {episode_title})"


class AssistantGMClaim(SharedMemoryModel):
    """An Assistant GM's claim on a specific beat session.

    Flow: AGM submits (status=REQUESTED) -> Lead GM or Staff approves or
    rejects -> AGM runs the session and marks the beat outcome ->
    Lead GM marks COMPLETED.

    Scope: the AGM sees only this beat + Lead-GM-flagged notes + the
    framing_note written for the session. They do NOT see the rest of
    the story plan.
    """

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="assistant_claims",
    )
    assistant_gm = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.CASCADE,
        related_name="assistant_claims_made",
    )
    status = models.CharField(
        max_length=20,
        choices=AssistantClaimStatus.choices,
        default=AssistantClaimStatus.REQUESTED,
    )
    approved_by = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assistant_claims_approved",
        help_text="The Lead GM or Staff member who approved/rejected.",
    )
    rejection_note = models.TextField(
        blank=True,
        help_text="Reason for rejection (shown to AGM).",
    )
    framing_note = models.TextField(
        blank=True,
        help_text=(
            "Lead GM's one-paragraph framing for the AGM session. Sets the "
            "scene without exposing the rest of the story."
        ),
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["beat", "assistant_gm"],
                condition=models.Q(
                    status__in=[AssistantClaimStatus.REQUESTED, AssistantClaimStatus.APPROVED]
                ),
                name="unique_active_claim_per_beat_per_agm",
            )
        ]
        indexes = [
            models.Index(fields=["status", "requested_at"]),
            models.Index(fields=["beat", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"AssistantGMClaim(beat=#{self.beat_id},"
            f" agm=#{self.assistant_gm_id}, status={self.status})"
        )
