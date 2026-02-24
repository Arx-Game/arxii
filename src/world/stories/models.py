from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

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


class Story(models.Model):
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

    # Ownership and management
    owners = models.ManyToManyField(
        "accounts.AccountDB",
        related_name="owned_stories",
        help_text="Players who own and can manage this story",
    )
    active_gms = models.ManyToManyField(
        "objects.ObjectDB",
        related_name="gm_stories",
        limit_choices_to={"db_typeclass_path__contains": "GMCharacter"},
        help_text="GM characters currently running this story",
    )

    # Trust requirements - stories can require trust in specific categories
    required_trust_categories = models.ManyToManyField(
        TrustCategory,
        through="StoryTrustRequirement",
        blank=True,
        help_text="Trust categories required to participate in this story",
    )

    # Story metadata
    is_personal_story = models.BooleanField(
        default=False,
        help_text="True if this is a character's personal story arc",
    )
    personal_story_character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_story",
        help_text="Character this personal story belongs to",
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


class StoryTrustRequirement(models.Model):
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


class StoryParticipation(models.Model):
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


class Chapter(models.Model):
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


class Episode(models.Model):
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
    connection_to_next = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        blank=True,
        help_text="How this episode connects to the next",
    )
    connection_summary = models.TextField(
        blank=True,
        help_text="Explanation of how episodes connect",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["chapter", "order"]
        ordering = ["chapter", "order"]

    def __str__(self) -> str:
        chapter = cast(Any, self.chapter)
        return f"{chapter.story.title} - Ep {self.order}: {self.title}"


class EpisodeScene(models.Model):
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

    # Scene connection tracking within episode
    connection_to_next = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        blank=True,
        help_text="How this scene connects to the next in the episode",
    )
    connection_summary = models.TextField(
        blank=True,
        help_text="Brief explanation of the scene connection",
    )

    class Meta:
        unique_together = ["episode", "scene"]
        ordering = ["episode", "order"]

    def __str__(self) -> str:
        return f"{self.episode} - Scene {self.order}"


class PlayerTrust(models.Model):
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


class PlayerTrustLevel(models.Model):
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


class StoryFeedback(models.Model):
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


class TrustCategoryFeedbackRating(models.Model):
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
