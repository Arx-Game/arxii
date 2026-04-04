"""Models for character-to-character relationships with track-based progression."""

from __future__ import annotations

from datetime import timedelta
from functools import cached_property
import math

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.relationships.constants import (
    DECAY_DAYS,
    FirstImpressionColoring,
    ReferenceMode,
    TrackSign,
    UpdateVisibility,
)


class RelationshipCondition(SharedMemoryModel):
    """
    Conditions that can exist on a relationship.

    These represent specific states or feelings one character has toward another,
    such as "Attracted To", "Fears", "Trusts", etc. Conditions gate which
    situational modifiers (from distinctions, magic, etc.) apply during
    roll resolution.

    Examples:
    - "Attracted To" gates the Allure modifier from the Attractive distinction
    - "Fears" gates intimidation-related modifiers
    - "Trusts" gates persuasion-related modifiers
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Condition name (e.g., 'Attracted To', 'Fears', 'Trusts')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this condition represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    # Which modifiers does this condition gate?
    gates_modifiers = models.ManyToManyField(
        "mechanics.ModifierTarget",
        blank=True,
        related_name="gated_by_conditions",
        help_text="Modifier types that only apply when this condition exists",
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_gates_modifiers(self) -> list:
        """Modifier targets gated by this condition. Supports Prefetch(to_attr=)."""
        return list(self.gates_modifiers.all())


class RelationshipTrack(SharedMemoryModel):
    """
    A named axis along which a relationship can develop.

    Tracks represent different dimensions of how characters relate to each other,
    such as Trust, Respect, Rivalry, or Fear. Each track has a sign indicating
    whether it represents positive or negative feelings.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Track name (e.g., 'Trust', 'Respect', 'Rivalry', 'Fear')",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this track",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this track represents",
    )
    sign = models.CharField(
        max_length=20,
        choices=TrackSign.choices,
        help_text="Whether this track represents positive or negative feelings",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_tiers(self) -> list[RelationshipTier]:
        """Tiers for this track. Supports Prefetch(to_attr=)."""
        return list(self.tiers.all())


class RelationshipTier(SharedMemoryModel):
    """
    A milestone level within a relationship track.

    Tiers represent significant thresholds of progression along a track,
    unlocking narrative and mechanical effects. For example, Trust track
    might have tiers like "Wary" (0), "Acquaintance" (10), "Confidant" (50).
    """

    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.CASCADE,
        related_name="tiers",
        help_text="The track this tier belongs to",
    )
    name = models.CharField(
        max_length=100,
        help_text="Tier name (e.g., 'Wary', 'Acquaintance', 'Confidant')",
    )
    tier_number = models.PositiveIntegerField(
        help_text="Numeric rank of this tier within the track (0 = lowest)",
    )
    point_threshold = models.PositiveIntegerField(
        help_text="Minimum points required to reach this tier",
    )
    description = models.TextField(
        blank=True,
        help_text="Narrative description of what this tier represents",
    )
    mechanical_bonus_description = models.TextField(
        blank=True,
        help_text="Description of mechanical bonuses unlocked at this tier",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["track", "tier_number"], name="unique_tier_per_track"),
        ]
        ordering = ["track", "tier_number"]

    def __str__(self) -> str:
        return f"{self.track.name} - {self.name} (Tier {self.tier_number})"


class HybridRelationshipType(SharedMemoryModel):
    """
    A special relationship type unlocked by meeting thresholds on multiple tracks.

    Hybrid types represent complex emotional states that emerge from combinations
    of track progression. For example, "Rivalry" might require both high Respect
    and high Antagonism.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Hybrid type name (e.g., 'Rivalry', 'Devotion')",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this hybrid type",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this hybrid type represents",
    )
    mechanical_bonus_description = models.TextField(
        blank=True,
        help_text="Description of mechanical bonuses granted by this hybrid type",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_requirements(self) -> list[HybridRequirement]:
        """Requirements for this hybrid type. Supports Prefetch(to_attr=)."""
        return list(self.requirements.select_related("track"))


class HybridRequirement(SharedMemoryModel):
    """
    A single track/tier requirement for unlocking a hybrid relationship type.

    Each hybrid type has one or more requirements specifying which tracks
    must reach which minimum tier for the hybrid to activate.
    """

    hybrid_type = models.ForeignKey(
        HybridRelationshipType,
        on_delete=models.CASCADE,
        related_name="requirements",
        help_text="The hybrid type this requirement belongs to",
    )
    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.CASCADE,
        help_text="The track that must meet the minimum tier",
    )
    minimum_tier = models.PositiveIntegerField(
        help_text="The minimum tier number that must be reached on this track",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hybrid_type", "track"], name="unique_track_per_hybrid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.hybrid_type.name} requires {self.track.name} >= Tier {self.minimum_tier}"


class CharacterRelationship(SharedMemoryModel):
    """
    One character's relationship toward another, tracked across multiple dimensions.

    Relationships use a track-based progression system where points accumulate
    along different axes (Trust, Respect, Fear, etc.). Characters can display
    a different track/tier than their actual one (deceit mechanics), and
    relationships require mutual consent (is_pending) before becoming active.
    """

    source = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="relationships_as_source",
        help_text="The character who holds this relationship",
    )
    target = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="relationships_as_target",
        help_text="The character this relationship is about",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this relationship is currently active",
    )
    is_pending = models.BooleanField(
        default=True,
        help_text="Whether this relationship is awaiting mutual consent",
    )

    # Deceit mechanics: what the character publicly displays
    displayed_track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Track displayed publicly (for deceit); null = show actual",
    )
    displayed_tier = models.ForeignKey(
        RelationshipTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Tier displayed publicly (for deceit); null = show actual",
    )
    is_deceitful = models.BooleanField(
        default=False,
        help_text="Whether the displayed track/tier differs from the actual values",
    )

    # Conditions on this relationship
    conditions = models.ManyToManyField(
        RelationshipCondition,
        blank=True,
        related_name="character_relationships",
        help_text="Conditions that exist on this relationship",
    )

    # Weekly rate limiting
    game_week = models.ForeignKey(
        "game_clock.GameWeek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="relationships",
        help_text="GameWeek these weekly counters belong to",
    )
    developments_this_week = models.PositiveIntegerField(
        default=0,
        help_text="Number of development updates submitted this week (max 7)",
    )
    changes_this_week = models.PositiveIntegerField(
        default=0,
        help_text="Number of relationship changes submitted this week",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this relationship was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this relationship was last modified",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_relationship_pair"),
        ]

    def __str__(self) -> str:
        return f"{self.source} -> {self.target}"

    def clean(self) -> None:
        """Validate relationship constraints."""
        super().clean()
        if self.source_id is not None and self.source_id == self.target_id:
            msg = "A character cannot have a relationship with themselves."
            raise ValidationError(msg)
        if self.displayed_tier_id and self.displayed_track_id:
            if self.displayed_tier.track_id != self.displayed_track_id:
                msg = "Displayed tier must belong to displayed track."
                raise ValidationError(msg)

    @property
    def cached_track_progress(self) -> list[RelationshipTrackProgress]:
        """Track progress entries. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_track_progress
        except AttributeError:
            return list(self.track_progress.select_related("track"))

    @cached_track_progress.setter
    def cached_track_progress(self, value: list[RelationshipTrackProgress]) -> None:
        """Allow Prefetch(to_attr='cached_track_progress') to set this."""
        self._cached_track_progress = value

    @property
    def cached_updates(self) -> list[RelationshipUpdate]:
        """Relationship updates. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_updates
        except AttributeError:
            return list(self.updates.all())

    @cached_updates.setter
    def cached_updates(self, value: list[RelationshipUpdate]) -> None:
        """Allow Prefetch(to_attr='cached_updates') to set this."""
        self._cached_updates = value

    @property
    def cached_conditions(self) -> list[RelationshipCondition]:
        """Conditions on this relationship. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_conditions
        except AttributeError:
            return list(self.conditions.all())

    @cached_conditions.setter
    def cached_conditions(self, value: list[RelationshipCondition]) -> None:
        """Allow Prefetch(to_attr='cached_conditions') to set this."""
        self._cached_conditions = value

    @property
    def absolute_value(self) -> int:
        """Total points across all tracks including temporary (unsigned sum)."""
        return sum(tp.total_points for tp in self.cached_track_progress)

    @property
    def developed_absolute_value(self) -> int:
        """Sum of developed (permanent) points across all tracks."""
        return sum(tp.developed_points for tp in self.cached_track_progress)

    @property
    def mechanical_bonus(self) -> float:
        """Cube root of absolute developed value — modest mechanical bonus."""
        return round(math.pow(self.developed_absolute_value, 1 / 3), 1)

    @property
    def affection(self) -> int:
        """Signed sum: positive tracks add, negative tracks subtract."""
        total = 0
        for tp in self.cached_track_progress:
            if tp.track.sign == TrackSign.POSITIVE:
                total += tp.total_points
            else:
                total -= tp.total_points
        return total


class RelationshipTrackProgress(SharedMemoryModel):
    """
    Points accumulated on a specific track within a character relationship.

    Tracks two types of points:
    - **capacity**: Maximum developed points allowed (increased by updates and capstones)
    - **developed_points**: Permanent points (from development updates and capstones)

    Temporary points are derived from active RelationshipUpdate records on this track,
    decaying linearly over DECAY_DAYS.
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="track_progress",
        help_text="The relationship this progress belongs to",
    )
    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.CASCADE,
        help_text="The track being progressed",
    )
    capacity = models.PositiveIntegerField(
        default=0,
        help_text="Maximum developed points allowed on this track",
    )
    developed_points = models.PositiveIntegerField(
        default=0,
        help_text="Permanent points earned through development and capstones",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "track"], name="unique_progress_per_track"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.relationship} - {self.track.name}: {self.developed_points}/{self.capacity}"

    @property
    def temporary_points(self) -> int:
        """Sum of current temporary contributions from all updates on this track.

        Uses cached_updates (populated by Prefetch(to_attr=) or property
        fallback) to avoid N+1 queries.
        """
        now = timezone.now()
        track_id = self.track_id
        total = 0
        for update in self.relationship.cached_updates:
            if update.track_id == track_id:
                total += update.current_temporary_value(now)
        return total

    @property
    def total_points(self) -> int:
        """Developed + temporary points."""
        return self.developed_points + self.temporary_points

    @property
    def current_tier(self) -> RelationshipTier | None:
        """Return the highest tier where point_threshold <= developed_points, or None."""
        return (
            self.track.tiers.filter(point_threshold__lte=self.developed_points)
            .order_by("-tier_number")
            .first()
        )


class RelationshipUpdate(SharedMemoryModel):
    """
    A narrative writeup that adds temporary points and capacity to a track.

    Updates are unlimited and represent significant moments. The points_earned
    value sets both the capacity increase (permanent) and the temporary point
    contribution (decays linearly over DECAY_DAYS).
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="updates",
        help_text="The relationship this update applies to",
    )
    author = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        help_text="The character who wrote this update",
    )
    title = models.CharField(
        max_length=200,
        help_text="Brief title summarizing the update",
    )
    writeup = models.TextField(
        help_text="Narrative writeup describing how the relationship developed",
    )
    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.PROTECT,
        help_text="The track that gains points from this update",
    )
    points_earned = models.PositiveIntegerField(
        help_text="Points earned: increases capacity and sets temporary value base",
    )
    coloring = models.CharField(
        max_length=20,
        choices=FirstImpressionColoring.choices,
        blank=True,
        help_text="Emotional coloring for first impressions (blank for normal updates)",
    )
    visibility = models.CharField(
        max_length=20,
        choices=UpdateVisibility.choices,
        default=UpdateVisibility.SHARED,
        help_text="Who can see this update",
    )
    is_first_impression = models.BooleanField(
        default=False,
        help_text="Whether this is a first impression update",
    )
    linked_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional scene this update is based on",
    )
    linked_interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="referencing_updates",
        help_text="Specific interaction this update references (no DB FK constraint "
        "— partitioned table, application-level integrity)",
    )
    reference_mode = models.CharField(
        max_length=30,
        choices=ReferenceMode.choices,
        default=ReferenceMode.ALL_WEEKLY,
        help_text="How this update references RP",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this update was created",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Update: {self.title} ({self.relationship})"

    def clean(self) -> None:
        """Validate coloring is set for first impressions and blank otherwise."""
        super().clean()
        if self.is_first_impression and not self.coloring:
            msg = "First impression updates must have an emotional coloring."
            raise ValidationError(msg)
        if not self.is_first_impression and self.coloring:
            msg = "Only first impression updates may have an emotional coloring."
            raise ValidationError(msg)

    def current_temporary_value(self, now: timezone.datetime | None = None) -> int:
        """Calculate remaining temporary points based on linear decay.

        Decays at 10% of original per day, reaching zero after DECAY_DAYS.
        """
        if now is None:
            now = timezone.now()
        elapsed = now - self.created_at
        days = elapsed / timedelta(days=1)
        if days >= DECAY_DAYS:
            return 0
        remaining = self.points_earned - (self.points_earned * days / DECAY_DAYS)
        return max(0, int(remaining))


class RelationshipDevelopment(SharedMemoryModel):
    """
    A development update that adds permanent points to a track.

    Limited to 7 per week across all relationships. Involves a social roll
    to determine points earned, up to the track's current capacity. Awards
    XP to the character.
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="developments",
        help_text="The relationship this development applies to",
    )
    author = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        help_text="The character who performed this development",
    )
    title = models.CharField(
        max_length=200,
        help_text="Brief title summarizing the development",
    )
    writeup = models.TextField(
        help_text="Narrative writeup describing the reflection or development",
    )
    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.PROTECT,
        help_text="The track that gains permanent points",
    )
    points_earned = models.PositiveIntegerField(
        help_text="Permanent points added to the track (up to capacity)",
    )
    xp_awarded = models.PositiveIntegerField(
        default=0,
        help_text="XP awarded to the character for this development",
    )
    visibility = models.CharField(
        max_length=20,
        choices=UpdateVisibility.choices,
        default=UpdateVisibility.SHARED,
        help_text="Who can see this development",
    )
    linked_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional scene this development is based on",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this development was created",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Development: {self.title} ({self.relationship})"


class RelationshipCapstone(SharedMemoryModel):
    """
    A capstone event that adds both permanent points and capacity.

    Capstones represent truly monumental moments. They are always allowed
    (unlimited) and add to both developed_points and capacity simultaneously.
    Real mechanical power is gated behind magical tethers (future PR).
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="capstones",
        help_text="The relationship this capstone applies to",
    )
    author = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        help_text="The character who recorded this capstone",
    )
    title = models.CharField(
        max_length=200,
        help_text="Title of the monumental moment",
    )
    writeup = models.TextField(
        help_text="Narrative description of the capstone event",
    )
    track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.PROTECT,
        help_text="The track that gains points and capacity",
    )
    points = models.PositiveIntegerField(
        help_text="Points added to both capacity and developed_points",
    )
    visibility = models.CharField(
        max_length=20,
        choices=UpdateVisibility.choices,
        default=UpdateVisibility.SHARED,
        help_text="Who can see this capstone",
    )
    linked_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional scene this capstone is based on",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this capstone was recorded",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Capstone: {self.title} ({self.relationship})"


class RelationshipChange(SharedMemoryModel):
    """
    A narrative writeup that moves developed points from one track to another.

    Changes represent shifts in how a character feels about another,
    transferring permanent points between tracks to reflect evolving
    dynamics.
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="changes",
        help_text="The relationship this change applies to",
    )
    author = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        help_text="The character who authored this change",
    )
    title = models.CharField(
        max_length=200,
        help_text="Brief title summarizing the change",
    )
    writeup = models.TextField(
        help_text="Narrative writeup describing why the relationship changed",
    )
    source_track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.PROTECT,
        related_name="changes_from",
        help_text="The track losing points",
    )
    target_track = models.ForeignKey(
        RelationshipTrack,
        on_delete=models.PROTECT,
        related_name="changes_to",
        help_text="The track gaining points",
    )
    points_moved = models.PositiveIntegerField(
        help_text="Number of points moved between tracks",
    )
    visibility = models.CharField(
        max_length=20,
        choices=UpdateVisibility.choices,
        default=UpdateVisibility.SHARED,
        help_text="Who can see this change",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this change was created",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Change: {self.title} ({self.relationship})"
