from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.character_sheets.types import LifecycleState
from world.societies.constants import RenownRisk
from world.stories.constants import (
    AssistantClaimStatus,
    BeatKind,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    EraStatus,
    ProgressStatus,
    SessionRequestStatus,
    StakeOutcomeMethod,
    StakeResolutionColumn,
    StakeRewardSink,
    StakeSeverity,
    StakeSubjectKind,
    StoryGMOfferStatus,
    StoryMaturity,
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

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
ACCOUNT_DB_MODEL = "accounts.AccountDB"
CONSEQUENCE_POOL_MODEL = "actions.ConsequencePool"
STORY_BEAT_MODEL = "stories.Beat"
STAKE_MODEL = "stories.Stake"

# Foreclosure wrap-up annotation: the nullable resolved_at/resolved_by pair shared
# by all three progress models (StoryProgress / GroupStoryProgress / GlobalStoryProgress).
# FORECLOSED stays the honest terminal status; a non-null resolved_at marks a staff
# wrap-up layered on top. Factored to avoid triplicated field literals (SonarCloud
# duplication gate). `related_name` differs per model.
_RESOLVED_AT_HELP = (
    "When a FORECLOSED thread was wrapped up by staff; null = not yet wrapped up. "
    "FORECLOSED stays the honest terminal status; a non-null resolved_at marks "
    "the closure process layered on top."
)
_RESOLVED_BY_HELP = "GMProfile that wrapped up this foreclosed thread."


def _foreclosure_resolution_fields(related_name: str) -> dict[str, object]:
    """Build the resolved_at + resolved_by field pair for a progress model."""
    return {
        "resolved_at": models.DateTimeField(null=True, blank=True, help_text=_RESOLVED_AT_HELP),
        "resolved_by": models.ForeignKey(
            "gm.GMProfile",
            null=True,
            blank=True,
            on_delete=models.SET_NULL,
            related_name=related_name,
            help_text=_RESOLVED_BY_HELP,
        ),
    }


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
        ACCOUNT_DB_MODEL,
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
    summary = models.TextField(
        blank=True,
        help_text=(
            "Player-facing 'The Story So Far' — GM-maintained running recap "
            "of what has happened and what may lie ahead. Surfaced to players "
            "via the role-gated story log, maturity-gated. NOT auto-generated."
        ),
    )
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
        default=StoryScope.UNASSIGNED,
        help_text=(
            "Whether this story belongs to one character (CHARACTER), "
            "a covenant/group (GROUP), or the whole metaplot (GLOBAL)."
        ),
    )
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
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
    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="storylines",
        help_text=(
            "For GROUP-scope stories: the covenant this storyline belongs to. "
            "Informational — not a credit gate. SET_NULL on covenant delete so "
            "an archived covenant doesn't cascade-delete its stories."
        ),
    )

    # Ownership and management
    owners = models.ManyToManyField(
        ACCOUNT_DB_MODEL,
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

    @cached_property
    def owner_account_ids(self) -> frozenset[int]:
        """Cached set of owning AccountDB pks.

        One query on first access, then reused for the life of this
        identity-mapped Story instance (so the GM-text gate does not
        issue an owners query per serialization).

        This is identity-map cached, so any code path that mutates the
        ``owners`` m2m MUST call :meth:`invalidate_owner_cache` afterwards
        or a subsequent GM-text-gate read on the same in-memory instance
        will see the stale set.
        """
        return frozenset(cast(Any, self).owners.values_list("pk", flat=True))

    def invalidate_owner_cache(self) -> None:
        """Clear the cached ``owner_account_ids`` set.

        Call this after any code path that mutates the story's ``owners``
        m2m (add/remove/set/clear) so subsequent reads of
        ``owner_account_ids`` (and thus the ``_gm_text_gate`` owner check)
        reflect the mutation. Mirrors the
        ``CharacterSheet.invalidate_class_level_cache`` convention.

        Example::

            story.owners.add(account)
            story.invalidate_owner_cache()
        """
        self.__dict__.pop("owner_account_ids", None)

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
        ACCOUNT_DB_MODEL,
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
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
    )
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
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
    )
    resting_conclusion = models.TextField(
        blank=True,
        help_text=(
            "Player-facing text shown when progress RESTS at this episode "
            "(no chosen transition). Required before PLOT promotion."
        ),
    )
    is_ending = models.BooleanField(
        default=False,
        help_text="Explicit 'this is an ending' marker; satisfies PLOT "
        "promotion when there is no outbound transition.",
    )
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
        ACCOUNT_DB_MODEL,
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
        ACCOUNT_DB_MODEL,
        on_delete=models.CASCADE,
        related_name="given_feedback",
    )
    reviewed_player = models.ForeignKey(
        ACCOUNT_DB_MODEL,
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
    required_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For FACTION_STANDING_AT_LEAST predicates (society-level).",
    )
    required_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="For FACTION_STANDING_AT_LEAST predicates (organization-level).",
    )
    required_standing = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "For FACTION_STANDING_AT_LEAST predicates — minimum raw "
            "SocietyReputation/OrganizationReputation.value (-1000..1000)."
        ),
    )

    # Phase 5b.3: authoring-time side of the stories-missions seam. A Beat
    # MAY name a MissionTemplate it requires; the engine that walks this FK
    # to flip the Beat when a launched instance terminates is deferred to a
    # future stories-missions seam design pass (the 5b.3 service
    # ``world.missions.services.beat.on_mission_complete_for_beat`` only
    # stub-records the trigger). The FK is independent of
    # ``predicate_type`` in 5b.3 — predicate-type-vs-required_mission
    # interaction is one of the deferred design questions; ``clean()`` does
    # not yet constrain it. SET_NULL on template delete: losing the
    # MissionTemplate must not also lose the Beat.
    required_mission = models.ForeignKey(
        "missions.MissionTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Optional: a MissionTemplate this beat requires (Phase 5b.3 data "
            "shape only; engine deferred). SET_NULL on template delete."
        ),
    )

    # Consequence pools for beat outcomes (nullable; authoring is opt-in).
    success_consequences = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="success_beats",
        help_text="ConsequencePool to fire when this beat resolves SUCCESS.",
    )
    failure_consequences = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="failure_beats",
        help_text="ConsequencePool to fire when this beat resolves FAILURE.",
    )
    expired_consequences = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expired_beats",
        help_text="ConsequencePool to fire when this beat resolves EXPIRED.",
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
    kind = models.CharField(
        max_length=12,
        choices=BeatKind.choices,
        default=BeatKind.TASK,
    )
    advances = models.BooleanField(
        default=True,
        help_text="False = Tangent: recorded for history, never gates a transition.",
    )
    risk = models.CharField(
        max_length=10,
        choices=RenownRisk.choices,
        default=RenownRisk.NONE,
        help_text=(
            "Stakes declaration — how life-threatening/consequential this beat is. "
            "Drives Legend award magnitude on SUCCESS (see "
            "world.societies.constants.RISK_LEGEND_AWARDS). Authoring trust-gated "
            "in the serializer."
        ),
    )
    target_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The character level this beat's stakes are declared against "
            "('EXTREME at level 4'). Effective risk at activation is computed "
            "from the gap between this and the actual party's average level. "
            "Required (via readiness validation, not clean()) when risk != NONE."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["episode", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["episode", "predicate_type", "required_condition_template"],
                name="unique_beat_per_episode_predicate_template",
                condition=models.Q(required_condition_template__isnull=False),
            ),
        ]
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
        BeatPredicateType.FACTION_STANDING_AT_LEAST: ("required_standing",),
    }

    def _required_config_fields(self) -> tuple[str, ...]:
        """Return the set of config fields required for this beat's predicate_type.

        For STORY_AT_MILESTONE, the required fields depend on referenced_milestone_type.
        For FACTION_STANDING_AT_LEAST, required_society/required_organization are an
        XOR pair (exactly one, whichever is set) rather than unconditionally required —
        include whichever one is populated so the "must be null elsewhere" check below
        doesn't reject the one legitimately in use; the XOR itself is enforced in clean().
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
        if self.predicate_type == BeatPredicateType.FACTION_STANDING_AT_LEAST:
            base = self._REQUIRED_CONFIG[BeatPredicateType.FACTION_STANDING_AT_LEAST]
            if self.required_society_id is not None:
                base = (*base, "required_society")
            if self.required_organization_id is not None:
                base = (*base, "required_organization")
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
            "required_society",
            "required_organization",
            "required_standing",
        }
        for field_name in all_config_fields - set(required):
            val = getattr(self, field_name)
            if val is not None and val != "":
                errors[field_name] = f"Must be null when predicate_type is {self.predicate_type}."
        if self.predicate_type == BeatPredicateType.FACTION_STANDING_AT_LEAST:
            has_society = self.required_society_id is not None
            has_org = self.required_organization_id is not None
            if has_society == has_org:  # neither set, or both set
                msg = (
                    "Exactly one of required_society or required_organization "
                    "must be set for FACTION_STANDING_AT_LEAST."
                )
                errors["required_society"] = msg
                errors["required_organization"] = msg
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
        STORY_BEAT_MODEL,
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
    """A beat outcome that must be satisfied for this transition to be eligible.

    Stake-level routing (#1770 PR2): when ``stake`` is set, the requirement is
    satisfied by the stake's StakeOutcome having
    ``column == required_stake_column`` instead of the beat's coarse outcome —
    so one beat's stakes can route to different downstream episodes. A
    stake-level row leaves ``required_outcome`` blank (exactly one of the two
    predicates is populated; ``clean`` enforces it).
    """

    transition = models.ForeignKey(
        "stories.Transition",
        on_delete=models.CASCADE,
        related_name="required_outcomes",
    )
    beat = models.ForeignKey(
        STORY_BEAT_MODEL,
        on_delete=models.CASCADE,
        related_name="routing_for_transitions",
    )
    required_outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
        blank=True,
        default="",
        help_text="Required beat outcome; blank on stake-level rows.",
    )
    stake = models.ForeignKey(
        STAKE_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="routing_for_transitions",
        help_text=(
            "When set, this requirement routes on the stake's "
            "StakeOutcome column instead of the beat's outcome."
        ),
    )
    required_stake_column = models.CharField(
        max_length=12,
        choices=StakeResolutionColumn.choices,
        blank=True,
        default="",
        help_text="Required StakeOutcome column; only with stake set.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transition", "beat"],
                condition=models.Q(stake__isnull=True),
                name="unique_routing_req_per_transition_beat",
            ),
            models.UniqueConstraint(
                fields=["transition", "stake"],
                condition=models.Q(stake__isnull=False),
                name="unique_routing_req_per_transition_stake",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.stake_id is not None:
            if not self.required_stake_column:
                raise ValidationError({"required_stake_column": "Required when stake is set."})
            if self.required_outcome:
                msg = "Must be blank when stake is set (stake rows route on the stake column)."
                raise ValidationError({"required_outcome": msg})
            if self.stake.beat_id != self.beat_id:
                raise ValidationError(
                    {"stake": "The stake must belong to this requirement's beat."}
                )
        else:
            if not self.required_outcome:
                raise ValidationError({"required_outcome": "Required when stake is not set."})
            if self.required_stake_column:
                raise ValidationError({"required_stake_column": "Only allowed when stake is set."})

    def __str__(self) -> str:
        if self.stake_id is not None:
            return (
                f"Transition #{self.transition_id} requires stake #{self.stake_id}"
                f" = {self.required_stake_column}"
            )
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
    """Audit ledger row for each beat outcome applied to a progress record.

    Exactly one of character_sheet / gm_table / neither must be populated,
    matching the story's scope:
      - CHARACTER scope → character_sheet non-null, gm_table null.
      - GROUP scope     → gm_table non-null, character_sheet null.
      - GLOBAL scope    → both null (the story itself is the identifier).
    """

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="beat_completions",
        help_text=(
            "For CHARACTER-scope stories: the character whose progress recorded this completion."
        ),
    )
    gm_table = models.ForeignKey(
        "gm.GMTable",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="beat_completions",
        help_text=("For GROUP-scope stories: the GMTable whose progress recorded this completion."),
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
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beat_completions",
        help_text=(
            "Graded outcome tier for this completion, when driven by an external "
            "resolved check (combat encounter, mission route, decisive scene check) "
            "rather than a plain GM SUCCESS/FAILURE mark. Null for GM-marked and "
            "aggregate-threshold completions."
        ),
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
            models.Index(fields=["gm_table", "-recorded_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        scope = self.beat.episode.chapter.story.scope
        if scope == StoryScope.CHARACTER and not self.character_sheet_id:
            raise ValidationError({"character_sheet": "Required for CHARACTER-scope stories."})
        if scope == StoryScope.GROUP and not self.gm_table_id:
            raise ValidationError({"gm_table": "Required for GROUP-scope stories."})
        if scope == StoryScope.CHARACTER and self.gm_table_id:
            raise ValidationError({"gm_table": "Must be null for CHARACTER-scope stories."})
        if scope == StoryScope.GROUP and self.character_sheet_id:
            raise ValidationError({"character_sheet": "Must be null for GROUP-scope stories."})
        if scope == StoryScope.GLOBAL and self.character_sheet_id:
            raise ValidationError({"character_sheet": "Must be null for GLOBAL-scope stories."})
        if scope == StoryScope.GLOBAL and self.gm_table_id:
            raise ValidationError({"gm_table": "Must be null for GLOBAL-scope stories."})

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
    status = models.CharField(
        max_length=16,
        choices=ProgressStatus.choices,
        default=ProgressStatus.ACTIVE,
    )
    resolved_at, resolved_by = _foreclosure_resolution_fields("group_progress_resolved").values()

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
    status = models.CharField(
        max_length=16,
        choices=ProgressStatus.choices,
        default=ProgressStatus.ACTIVE,
    )
    resolved_at, resolved_by = _foreclosure_resolution_fields("global_progress_resolved").values()

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
    status = models.CharField(
        max_length=16,
        choices=ProgressStatus.choices,
        default=ProgressStatus.ACTIVE,
    )
    resolved_at, resolved_by = _foreclosure_resolution_fields(
        "character_progress_resolved"
    ).values()

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


class StoryNote(SharedMemoryModel):
    """Append-only OOC authorial memory attached to a Story.

    General story notes + future-idea seeds. Distinct from per-node pitch
    text. Never player-visible. Not promotable — purely informational for
    the next author. No edit/delete in the API.
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="notes")
    author_account = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"StoryNote(story={self.story_id}, at={self.created_at})"


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


class SessionRequest(SharedMemoryModel):
    """A scheduling request generated when an episode becomes ready-to-run.

    Flow:
        Episode becomes eligible -> SessionRequest(status=OPEN) created
        -> Lead GM / player (per scope) turns it into an Event via the
        events app -> SessionRequest.status=SCHEDULED, event populated
        -> session runs, beats marked, episode resolved
        -> SessionRequest.status=RESOLVED

    Player-scope interaction:
        CHARACTER: initiator is the story's character's account; may open
        to first-available GM via open_to_any_gm=True.
        GROUP: initiator is the Lead GM coordinating the group.
        GLOBAL: initiator is staff; open_to_any_gm typically True.
    """

    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name="session_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=SessionRequestStatus.choices,
        default=SessionRequestStatus.OPEN,
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session_requests",
        help_text=(
            "Populated when the Lead GM schedules this via create_event_from_session_request."
        ),
    )
    open_to_any_gm = models.BooleanField(
        default=False,
        help_text=(
            "Player opted for first-available GM (CHARACTER scope only), or "
            "staff opened a metaplot event to any GM."
        ),
    )
    assigned_gm = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_session_requests",
        help_text="The GM currently expected to run this session.",
    )
    initiated_by_account = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="initiated_session_requests",
    )
    notes = models.TextField(
        blank=True,
        help_text="Player or staff notes (scheduling preferences, etc.).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["episode", "status"]),
            models.Index(fields=["assigned_gm", "status"]),
        ]

    @property
    def story(self) -> "Story":
        """Walk episode -> chapter -> story. Free via SharedMemoryModel identity map."""
        return self.episode.chapter.story

    def __str__(self) -> str:
        return f"SessionRequest({self.episode.title} status={self.status})"


class StoryGMOffer(SharedMemoryModel):
    """A player's offer to assign their personal story to a specific GM.

    Lifecycle:
        PENDING -> ACCEPTED  (GM takes the story; primary_table set)
                -> DECLINED  (GM rejects; story stays seeking)
                -> WITHDRAWN (player rescinds; story stays seeking)

    Only one PENDING offer per (story, offered_to) at a time
    (partial unique constraint).
    """

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="gm_offers",
    )
    offered_to = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.CASCADE,
        related_name="story_offers_received",
    )
    offered_by_account = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        on_delete=models.CASCADE,
        related_name="story_offers_made",
    )
    status = models.CharField(
        max_length=20,
        choices=StoryGMOfferStatus.choices,
        default=StoryGMOfferStatus.PENDING,
    )
    message = models.TextField(blank=True, help_text="Optional note from offerer.")
    response_note = models.TextField(blank=True, help_text="Optional GM response.")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "offered_to"],
                condition=models.Q(status=StoryGMOfferStatus.PENDING),
                name="unique_pending_offer_per_story_per_gm",
            )
        ]
        indexes = [
            models.Index(fields=["offered_to", "status"]),
            models.Index(fields=["story", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"StoryGMOffer(story=#{self.story_id}, gm=#{self.offered_to_id}, status={self.status})"
        )


# ---------------------------------------------------------------------------
# Wave 10: TableBulletinPost + TableBulletinReply
# ---------------------------------------------------------------------------


class TableBulletinPost(SharedMemoryModel):
    """A bulletin board post on a GMTable, optionally story-scoped.

    - story=None → table-wide post visible to all active table members
    - story=set  → story-scoped post visible to story participants only

    Top-level posts are authored by the table's Lead GM or staff (enforced
    in the serializer/permission layer). Replies are configurable per
    post via allow_replies.
    """

    table = models.ForeignKey(
        "gm.GMTable",
        on_delete=models.CASCADE,
        related_name="bulletin_posts",
    )
    story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bulletin_posts",
        help_text=(
            "If set, post is visible to story participants only. "
            "If null, post is visible to all active table members."
        ),
    )
    author_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,  # nullable so persona deletion does not cascade-delete history
        on_delete=models.SET_NULL,
        related_name="table_bulletin_posts",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    allow_replies = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["table", "story", "-created_at"]),
            models.Index(fields=["author_persona", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        story_label = f" (story #{self.story_id})" if self.story_id else " (table-wide)"
        return f"TableBulletinPost(#{self.pk}, table=#{self.table_id}{story_label})"


class TableBulletinReply(SharedMemoryModel):
    """A reply to a TableBulletinPost.

    Anyone with read access to the parent post can reply, IF the parent's
    allow_replies=True. Replies are flat (no nested replies) for v1.
    """

    post = models.ForeignKey(
        TableBulletinPost,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    author_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        on_delete=models.SET_NULL,
        related_name="table_bulletin_replies",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"TableBulletinReply(#{self.pk}, post=#{self.post_id})"


class RiskCalibration(SharedMemoryModel):
    """Designer-tunable calibration bands per risk tier (#1770 pillar 5).

    One row per RenownRisk tier above NONE. severity_floor_total is the minimum
    summed StakeSeverity a beat at this risk must wager (no fake stakes);
    severity_ceiling caps any single stake (no 'everyone dies' at LOW);
    max_fuse_hops is the chain rule — how many failure-cascade hops may
    separate this tier from reachable removal-from-play (EXTREME=0).
    reward_floor/reward_ceiling band the declared win-column reward value
    (consumed by PR3; stored now so calibration is one row, authored once).
    """

    risk = models.CharField(max_length=10, choices=RenownRisk.choices, unique=True)
    severity_floor_total = models.PositiveSmallIntegerField()
    severity_ceiling = models.PositiveSmallIntegerField(choices=StakeSeverity.choices)
    max_fuse_hops = models.PositiveSmallIntegerField()
    reward_floor = models.PositiveIntegerField(default=0)
    reward_ceiling = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["risk"]

    def __str__(self) -> str:
        return f"RiskCalibration({self.risk})"


class StakeTemplate(SharedMemoryModel):
    """Catalog row a GM instantiates a Stake from (#1770 pillar 5, menu-first).

    min_risk/max_risk bound which risk tiers may carry this template
    (compared by RISK_LADDER index, see services.stakes.risk_index).
    """

    name = models.CharField(max_length=100, unique=True)
    subject_kind = models.CharField(max_length=20, choices=StakeSubjectKind.choices)
    severity = models.PositiveSmallIntegerField(choices=StakeSeverity.choices)
    min_risk = models.CharField(max_length=10, choices=RenownRisk.choices, default=RenownRisk.LOW)
    max_risk = models.CharField(
        max_length=10, choices=RenownRisk.choices, default=RenownRisk.EXTREME
    )
    player_summary_template = models.TextField(
        help_text="Player-facing summary shown at opt-in; GM fills the specifics."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    content_themes = models.ManyToManyField(
        "boundaries.ContentTheme",
        blank=True,
        related_name="stake_templates",
        help_text=(
            "Content themes this template's staking would involve — matched against hard lines."
        ),
    )

    class Meta:
        ordering = ["subject_kind", "severity", "name"]

    def __str__(self) -> str:
        return f"StakeTemplate({self.name})"


class Stake(SharedMemoryModel):
    """One named wager on a Beat's stakes contract (#1770 pillar 1).

    Exactly one typed subject pointer (or subject_label for CUSTOM) names the
    concrete thing wagered. severity/subject_kind denormalize from template at
    creation (serializer) so a later template retune never rewrites live
    contracts.
    """

    beat = models.ForeignKey(STORY_BEAT_MODEL, on_delete=models.CASCADE, related_name="stakes")
    template = models.ForeignKey(
        "stories.StakeTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stakes",
        help_text="Null only for trust-gated custom stakes.",
    )
    subject_kind = models.CharField(max_length=20, choices=StakeSubjectKind.choices)
    severity = models.PositiveSmallIntegerField(choices=StakeSeverity.choices)
    # A Stake is story-significant data: it must outlive the deletion of its
    # subject. All four subject FKs are SET_NULL (never CASCADE) so a
    # consumed/deleted subject doesn't erase the wager — subject_label and
    # player_summary already carry the name for display after the pointer
    # goes null.
    subject_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For NPC_FATE / PERSONAL_JEOPARDY subjects. Nulls if the sheet is deleted.",
    )
    subject_item = models.ForeignKey(
        "items.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For ITEM subjects. Nulls if the item instance is deleted/consumed.",
    )
    subject_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For FACTION subjects (society-level). Nulls if the society is deleted.",
    )
    subject_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For FACTION subjects (organization-level). Nulls if the org is deleted.",
    )
    subject_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Freeform subject name (CUSTOM / CAMPAIGN_TRACK, or flavor).",
    )
    player_summary = models.TextField(
        help_text="Player-facing line shown at opt-in: what is wagered, how badly."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["beat", "-severity", "pk"]
        indexes = [models.Index(fields=["beat"])]

    def __str__(self) -> str:
        return f"Stake({self.get_subject_kind_display()}: {self.subject_label or self.pk})"


class StakeResolution(SharedMemoryModel):
    """Authored branch for one stake x one outcome column (#1770 pillar 1).

    Pillar 12 (no-fiat removal): the structured world-state writers below are
    validated so a branch can never remove a player character by fiat —
    sets_subject_lifecycle is only legal for NPC_FATE subjects whose sheet is
    not player-held; PC removal must route through peril (escalates_to_risk +
    consequence pools -> process_damage_consequences).
    """

    stake = models.ForeignKey(STAKE_MODEL, on_delete=models.CASCADE, related_name="resolutions")
    column = models.CharField(max_length=12, choices=StakeResolutionColumn.choices)
    outcome_key = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Short designer-authored slug naming this branch within its "
            "column's polarity (#1760) — e.g. 'destroyed', 'captured', "
            "'given_to_allies'. Blank = the column's single default branch "
            "(backward compatible with pre-#1760 content). column stays the "
            "coarse WIN/LOSS/WITHDRAWAL polarity every severity/reward/"
            "machine-grading rule keys off; outcome_key is a finer dimension "
            "within it, not a replacement axis."
        ),
    )
    consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Pool to fire when this column resolves (tier-aware).",
    )
    escalates_to_risk = models.CharField(
        max_length=10,
        choices=RenownRisk.choices,
        blank=True,
        default="",
        help_text=(
            "The risk tier the situation spawned by this branch carries — the "
            "fuse mechanic. Blank = no escalation declared."
        ),
    )
    narrative_summary = models.TextField(
        blank=True,
        help_text="What happens in the story when this branch fires (GM-authored).",
    )
    # World-state writers (#1770 PR2). Validated by StakeResolutionSerializer
    # (pillar 12: no-fiat removal) and applied by
    # world.stories.services.stake_resolution when the branch fires.
    forfeits_subject_item = models.BooleanField(
        default=False,
        help_text="On fire, soft-forfeit the stake's subject_item (ITEM stakes only).",
    )
    subject_standing_delta = models.SmallIntegerField(
        default=0,
        help_text=(
            "On fire, adjust standing between the stake's subject and each "
            "participant persona (#1760). NPC_FATE: adjusts NPCStanding via "
            "subject_sheet's primary persona (unchanged pre-#1760 behavior). "
            "FACTION: adjusts SocietyReputation or OrganizationReputation "
            "(whichever of subject_society/subject_organization is set) — "
            "previously a dead FK (subject_society/subject_organization were "
            "never read); this is the fix."
        ),
    )
    sets_subject_lifecycle = models.CharField(
        max_length=10,
        choices=LifecycleState.choices,
        blank=True,
        default="",
        help_text=(
            "On fire, set_lifecycle_state(subject_sheet, value). NPC_FATE only, "
            "and only when the subject sheet is not player-held (pillar 12)."
        ),
    )
    machine_match_lifecycle_state = models.CharField(
        max_length=10,
        choices=LifecycleState.choices,
        blank=True,
        default="",
        help_text=(
            "On automatic (machine) grading, if the stake's subject_sheet's "
            "actual lifecycle_state equals this value, THIS branch is "
            "selected over the column's plain default (#1760 — generalizes "
            "the old is-dead-only override to the full LifecycleState "
            "ladder: ALIVE/CAPTURED/COMA/RETIRED/DEAD). NPC_FATE stakes only "
            "— blank means no machine-match, resolve via the plain column "
            "default or a GM's Constrained Pick."
        ),
    )

    class Meta:
        ordering = ["stake", "column", "outcome_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["stake", "column", "outcome_key"],
                name="unique_resolution_per_stake_column_outcome_key",
            )
        ]

    def clean(self) -> None:
        """Pillar-12 payload validation (mirrored in StakeResolutionSerializer).

        Kept at the model level too so admin-inline authoring can't sidestep
        the no-fiat rule.
        """
        from world.stories.services.stake_resolution import (  # noqa: PLC0415
            stake_resolution_payload_problems,
        )

        super().clean()
        for problem in stake_resolution_payload_problems(
            stake=self.stake,
            forfeits_subject_item=self.forfeits_subject_item,
            subject_standing_delta=self.subject_standing_delta,
            sets_subject_lifecycle=self.sets_subject_lifecycle,
            machine_match_lifecycle_state=self.machine_match_lifecycle_state,
        ):
            raise ValidationError({problem.field: problem.message})

    def __str__(self) -> str:
        suffix = f"/{self.outcome_key}" if self.outcome_key else ""
        return f"StakeResolution({self.stake_id}:{self.column}{suffix})"


class StakeRewardLine(SharedMemoryModel):
    """One authored win-reward payout on a stake's WIN branch (#1770 PR3).

    Authored pre-scene alongside the branch it hangs off — WIN-column
    resolutions only, enforced in clean() + serializer (a "consolation" line
    on LOSS/WITHDRAWAL would be silently inert; an authoring foot-gun, not a
    feature). When the branch fires under a ready, effective-risk-bearing
    activation, EVERY completion participant receives each line's full amount
    (ALL_EQUAL semantics, mirroring mission reward distribution). ``amount``
    is a money-equivalent scalar for every sink so
    RiskCalibration.reward_floor/reward_ceiling can band the summed total per
    beat.
    """

    resolution = models.ForeignKey(
        "stories.StakeResolution",
        on_delete=models.CASCADE,
        related_name="reward_lines",
    )
    sink = models.CharField(max_length=12, choices=StakeRewardSink.choices)
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Money-equivalent scalar paid to EACH participant (banded by calibration).",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Required when sink=RESONANCE; must be null otherwise.",
    )

    class Meta:
        ordering = ["resolution", "pk"]

    def clean(self) -> None:
        """Sink/payload shape guard (mirrored in StakeRewardLineSerializer)."""
        super().clean()
        if self.resolution_id is not None and self.resolution.column != StakeResolutionColumn.WIN:
            raise ValidationError(
                {"resolution": "Reward lines only attach to WIN-column resolutions."}
            )
        if self.sink == StakeRewardSink.RESONANCE and self.resonance_id is None:
            raise ValidationError({"resonance": "Required when sink is RESONANCE."})
        if self.sink != StakeRewardSink.RESONANCE and self.resonance_id is not None:
            raise ValidationError({"resonance": "Only allowed when sink is RESONANCE."})

    def __str__(self) -> str:
        return f"StakeRewardLine({self.resolution_id}: {self.sink} x{self.amount})"


class StakeContractActivation(SharedMemoryModel):
    """The lock + audit row written when a staked scene starts (#1770 pillars 7-8).

    Lock-not-copy MVP: while an open activation exists (resolved_at null),
    serializers refuse edits to the beat's stakes/resolutions; resolution
    reads effective_risk off this row. Closed by the beat-completion tail.
    """

    beat = models.ForeignKey(
        STORY_BEAT_MODEL, on_delete=models.CASCADE, related_name="stake_activations"
    )
    locked_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    party_average_level = models.PositiveIntegerField()
    declared_target_level = models.PositiveIntegerField(
        default=0, help_text="Beat.target_level snapshot at activation (0 = unset)."
    )
    declared_risk = models.CharField(max_length=10, choices=RenownRisk.choices)
    effective_risk = models.CharField(
        max_length=10,
        choices=RenownRisk.choices,
        help_text="What Legend actually pays on — see compute_effective_risk.",
    )
    is_ready = models.BooleanField(
        help_text="Readiness verdict at activation; False forced effective NONE."
    )
    readiness_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-locked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["beat"],
                condition=models.Q(resolved_at__isnull=True),
                name="unique_open_activation_per_beat",
            )
        ]

    def __str__(self) -> str:
        state = "open" if self.resolved_at is None else "resolved"
        return f"StakeContractActivation({self.beat_id}, {state}, {self.effective_risk})"


class StakeOutcome(SharedMemoryModel):
    """Per-stake resolution audit + routing row (#1770 PR2).

    Mirrors EpisodeResolution (a GM narrative-decision audit) and
    BeatCompletion (an append-only ledger): **exactly one row per resolved
    stake** (unique constraint) — a stake's resolution fires once from the
    locked contract, whether by machine grading or a GM's constrained pick.
    ``resolution`` is null when no branch was authored for the chosen column
    (audit honesty: an unready contract that ran anyway). Transition routing
    (TransitionRequiredOutcome.required_stake_column) reads this row.
    """

    stake = models.ForeignKey(
        STAKE_MODEL,
        on_delete=models.CASCADE,
        related_name="outcomes",
    )
    activation = models.ForeignKey(
        "stories.StakeContractActivation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stake_outcomes",
        help_text="Which locked contract this outcome resolved under (audit).",
    )
    resolution = models.ForeignKey(
        "stories.StakeResolution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The authored branch that fired; null = no branch authored for the column.",
    )
    column = models.CharField(max_length=12, choices=StakeResolutionColumn.choices)
    method = models.CharField(max_length=12, choices=StakeOutcomeMethod.choices)
    resolved_by = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stake_outcomes",
        help_text="The GM who picked the column (GM_PICK only; null for MACHINE).",
    )
    gm_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["stake"], name="unique_outcome_per_stake")]

    def __str__(self) -> str:
        return f"StakeOutcome(stake={self.stake_id}, {self.column}, {self.method})"


class TreasuredSignoff(SharedMemoryModel):
    """A player's explicit pre-scene consent to stake one of their treasured
    subjects on a beat. Soft-withdrawal only (story-significant; never
    hard-deleted). Withdrawal mid-story routes the affected stake to the
    WITHDRAWAL column at completion."""

    beat = models.ForeignKey(
        STORY_BEAT_MODEL,
        on_delete=models.CASCADE,
        related_name="treasured_signoffs",
    )
    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="treasured_signoffs",
    )
    treasured_subject = models.ForeignKey(
        "boundaries.TreasuredSubject",
        on_delete=models.CASCADE,
        related_name="signoffs",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["beat", "player_data"]

    @property
    def active(self) -> bool:
        return self.withdrawn_at is None

    def __str__(self) -> str:
        status = "active" if self.active else "withdrawn"
        return f"TreasuredSignoff(beat={self.beat_id}, player={self.player_data_id}, {status})"


class StoryNPCDependency(SharedMemoryModel):
    """Declares that an NPC is load-bearing for a story.

    When active, the NPC is structurally protected from death by actors
    external to the story. See ``is_death_prevented_by_story`` in
    ``world.stories.npc_protection``.
    """

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="npc_dependencies",
    )
    npc_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="story_dependencies",
        help_text="The NPC character that is load-bearing for this story.",
    )
    beat = models.ForeignKey(
        Beat,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="npc_dependencies",
        help_text=(
            "For beat-level refinement: protection applies only while this "
            "beat is unsatisfied. Null = story-level (whole arc)."
        ),
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="GM notes on why this NPC is critical.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["story", "npc_sheet"]
        indexes = [
            models.Index(fields=["npc_sheet", "is_active"]),
        ]

    def __str__(self) -> str:
        scope = f"beat #{self.beat_id}" if self.beat_id else "story-level"
        return f"StoryNPCDependency(npc_sheet=#{self.npc_sheet_id}, {scope})"
