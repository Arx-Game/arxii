from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.gm.serializers import GMProfileSerializer
from world.scenes.models import Persona
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    SessionRequestStatus,
    StoryScope,
)
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    BeatCompletion,
    Chapter,
    Episode,
    EpisodeResolution,
    EpisodeScene,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    PlayerTrustLevel,
    SessionRequest,
    Story,
    StoryFeedback,
    StoryParticipation,
    StoryProgress,
    StoryTrustRequirement,
    Transition,
    TrustCategory,
    TrustCategoryFeedbackRating,
)
from world.stories.types import AnyStoryProgress, StoryLogBeatEntry, StoryLogEpisodeEntry


class StoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for story list views"""

    owners_count = serializers.IntegerField(source="owners.count", read_only=True)
    active_gms_count = serializers.IntegerField(
        source="active_gms.count",
        read_only=True,
    )
    participants_count = serializers.IntegerField(
        source="participants.filter(is_active=True).count",
        read_only=True,
    )

    class Meta:
        model = Story
        fields = [
            "id",
            "title",
            "status",
            "privacy",
            "scope",
            "owners_count",
            "active_gms_count",
            "participants_count",
            "created_at",
            "updated_at",
        ]


class StoryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for story detail views"""

    owners = serializers.StringRelatedField(many=True, read_only=True)
    active_gms = GMProfileSerializer(many=True, read_only=True)
    character_sheet = serializers.PrimaryKeyRelatedField(read_only=True)
    chapters_count = serializers.IntegerField(source="chapters.count", read_only=True)
    trust_requirements = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id",
            "title",
            "description",
            "status",
            "privacy",
            "scope",
            "owners",
            "active_gms",
            "trust_requirements",
            "character_sheet",
            "chapters_count",
            "created_at",
            "updated_at",
            "completed_at",
        ]

    def get_trust_requirements(self, obj):
        """Get trust requirements for this story"""
        return obj.get_trust_requirements_summary()


class StoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating stories"""

    class Meta:
        model = Story
        fields = [
            "title",
            "description",
            "privacy",
            "scope",
        ]

    # Title validation constants
    MIN_TITLE_LENGTH = 3
    MAX_TITLE_LENGTH = 200

    # Comment validation constants
    MIN_COMMENT_LENGTH = 10

    def validate_title(self, value):
        """Ensure title is not empty and has reasonable length"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Title must be at least 3 characters long"
            raise serializers.ValidationError(
                msg,
            )
        if len(value) > self.MAX_TITLE_LENGTH:
            msg = "Title cannot exceed 200 characters"
            raise serializers.ValidationError(msg)
        return value.strip()


class StoryParticipationSerializer(serializers.ModelSerializer):
    """Serializer for story participation"""

    story = serializers.StringRelatedField(read_only=True)
    character = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = StoryParticipation
        fields = [
            "id",
            "story",
            "character",
            "participation_level",
            "trusted_by_owner",
            "joined_at",
            "is_active",
        ]


class ChapterListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for chapter lists"""

    story = serializers.StringRelatedField(read_only=True)
    episodes_count = serializers.IntegerField(source="episodes.count", read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "story",
            "title",
            "order",
            "is_active",
            "episodes_count",
            "completed_at",
            "created_at",
        ]


class ChapterDetailSerializer(serializers.ModelSerializer):
    """Full serializer for chapter details"""

    story = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "story",
            "title",
            "description",
            "order",
            "is_active",
            "summary",
            "consequences",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class ChapterCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chapters"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Chapter
        fields = ["story", "title", "description", "order"]

    def validate_title(self, value):
        """Validate chapter title"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Chapter title must be at least 3 characters"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data: Any) -> Any:  # type: ignore[invalid-method-override]
        """Validate chapter order is unique within story"""
        story = data.get("story")
        order = data.get("order")

        if story and cast(Any, Chapter).objects.filter(story=story, order=order).exists():
            msg = f"Chapter with order {order} already exists for this story"
            raise serializers.ValidationError(
                msg,
            )

        return data


class EpisodeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for episode lists"""

    chapter = serializers.StringRelatedField(read_only=True)
    scenes_count = serializers.IntegerField(
        source="episode_scenes.count",
        read_only=True,
    )

    class Meta:
        model = Episode
        fields = [
            "id",
            "chapter",
            "title",
            "order",
            "is_active",
            "scenes_count",
            "completed_at",
        ]


class EpisodeDetailSerializer(serializers.ModelSerializer):
    """Full serializer for episode details"""

    chapter = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Episode
        fields = [
            "id",
            "chapter",
            "title",
            "description",
            "order",
            "is_active",
            "summary",
            "consequences",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class EpisodeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating episodes"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Episode
        fields = [
            "chapter",
            "title",
            "description",
            "order",
        ]

    def validate_title(self, value):
        """Validate episode title"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Episode title must be at least 3 characters"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data: Any) -> Any:  # type: ignore[invalid-method-override]
        """Validate episode order is unique within chapter"""
        chapter = data.get("chapter")
        order = data.get("order")

        if chapter and cast(Any, Episode).objects.filter(chapter=chapter, order=order).exists():
            msg = f"Episode with order {order} already exists for this chapter"
            raise serializers.ValidationError(
                msg,
            )

        return data


class EpisodeSceneSerializer(serializers.ModelSerializer):
    """Serializer for episode-scene connections"""

    episode = serializers.StringRelatedField(read_only=True)
    scene = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = EpisodeScene
        fields = [
            "id",
            "episode",
            "scene",
            "order",
        ]


class PlayerTrustSerializer(serializers.ModelSerializer):
    """Serializer for player trust profiles"""

    account = serializers.StringRelatedField(read_only=True)
    total_positive_feedback = serializers.ReadOnlyField()
    total_negative_feedback = serializers.ReadOnlyField()

    class Meta:
        model = PlayerTrust
        fields = [
            "id",
            "account",
            "gm_trust_level",
            "total_positive_feedback",
            "total_negative_feedback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "total_positive_feedback",
            "total_negative_feedback",
            "created_at",
            "updated_at",
        ]


class TrustCategorySerializer(serializers.ModelSerializer):
    """Serializer for trust categories"""

    class Meta:
        model = TrustCategory
        fields = [
            "id",
            "name",
            "display_name",
            "description",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class TrustCategoryFeedbackRatingSerializer(serializers.ModelSerializer):
    """Serializer for trust category feedback ratings"""

    trust_category = TrustCategorySerializer(read_only=True)

    class Meta:
        model = TrustCategoryFeedbackRating
        fields = ["id", "trust_category", "rating", "notes"]


class StoryFeedbackSerializer(serializers.ModelSerializer):
    """Serializer for story feedback"""

    MIN_COMMENT_LENGTH = StoryCreateSerializer.MIN_COMMENT_LENGTH
    story = serializers.StringRelatedField(read_only=True)
    reviewer = serializers.StringRelatedField(read_only=True)
    reviewed_player = serializers.StringRelatedField(read_only=True)
    category_ratings = TrustCategoryFeedbackRatingSerializer(many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    is_overall_positive = serializers.SerializerMethodField()

    class Meta:
        model = StoryFeedback
        fields = [
            "id",
            "story",
            "reviewer",
            "reviewed_player",
            "category_ratings",
            "average_rating",
            "is_overall_positive",
            "is_gm_feedback",
            "comments",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_average_rating(self, obj):
        """Get average rating across all categories"""
        return obj.get_average_rating()

    def get_is_overall_positive(self, obj):
        """Get whether feedback is overall positive"""
        return obj.is_overall_positive()

    def validate_comments(self, value):
        """Ensure feedback has meaningful content"""
        if len(value.strip()) < self.MIN_COMMENT_LENGTH:
            msg = "Feedback comments must be at least 10 characters long"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()


class TrustCategoryFeedbackRatingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating trust category feedback ratings"""

    class Meta:
        model = TrustCategoryFeedbackRating
        fields = ["trust_category", "rating", "notes"]

    def validate_rating(self, value):
        """Validate rating is within range"""
        if value not in [-2, -1, 0, 1, 2]:
            msg = "Rating must be between -2 and 2"
            raise serializers.ValidationError(msg)
        return value


class StoryFeedbackCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating story feedback with category ratings"""

    category_ratings = TrustCategoryFeedbackRatingCreateSerializer(many=True)
    MIN_COMMENT_LENGTH = StoryCreateSerializer.MIN_COMMENT_LENGTH

    class Meta:
        model = StoryFeedback
        fields = [
            "story",
            "reviewed_player",
            "is_gm_feedback",
            "comments",
            "category_ratings",
        ]

    def create(self, validated_data: dict[str, Any]) -> StoryFeedback:
        """Create feedback with category ratings"""
        category_ratings_data = validated_data.pop("category_ratings", [])
        feedback = cast(Any, StoryFeedback).objects.create(**validated_data)

        for rating_data in category_ratings_data:
            cast(Any, TrustCategoryFeedbackRating).objects.create(
                feedback=feedback,
                **rating_data,
            )

        return feedback

    def validate_comments(self, value):
        """Ensure feedback has meaningful content"""
        if len(value.strip()) < self.MIN_COMMENT_LENGTH:
            msg = "Feedback comments must be at least 10 characters long"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data: Any) -> Any:  # type: ignore[invalid-method-override]
        """Prevent self-feedback and duplicate feedback"""
        request = self.context.get("request")
        if request and request.user == data.get("reviewed_player"):
            msg = "You cannot provide feedback on yourself"
            raise serializers.ValidationError(msg)

        # Check for duplicate feedback
        story = data.get("story")
        reviewed_player = data.get("reviewed_player")
        if (
            request
            and cast(Any, StoryFeedback)
            .objects.filter(
                story=story,
                reviewer=request.user,
                reviewed_player=reviewed_player,
            )
            .exists()
        ):
            msg = "You have already provided feedback for this player in this story"
            raise serializers.ValidationError(
                msg,
            )

        return data


# Trust Category Serializers


class TrustCategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating trust categories"""

    class Meta:
        model = TrustCategory
        fields = ["name", "display_name", "description"]

    def validate_name(self, value):
        """Validate category name is slug-like"""
        if not value.replace("_", "").replace("-", "").isalnum():
            msg = "Category name should only contain letters, numbers, underscores, and hyphens"
            raise serializers.ValidationError(
                msg,
            )
        return value.lower()


class PlayerTrustLevelSerializer(serializers.ModelSerializer):
    """Serializer for individual trust levels"""

    player_trust = serializers.StringRelatedField(read_only=True)
    trust_category = TrustCategorySerializer(read_only=True)

    class Meta:
        model = PlayerTrustLevel
        fields = [
            "id",
            "player_trust",
            "trust_category",
            "trust_level",
            "positive_feedback_count",
            "negative_feedback_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "positive_feedback_count",
            "negative_feedback_count",
            "created_at",
            "updated_at",
        ]


class StoryTrustRequirementSerializer(serializers.ModelSerializer):
    """Serializer for story trust requirements"""

    trust_category = TrustCategorySerializer(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = StoryTrustRequirement
        fields = [
            "id",
            "trust_category",
            "minimum_trust_level",
            "notes",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class StoryTrustRequirementCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating story trust requirements"""

    class Meta:
        model = StoryTrustRequirement
        fields = ["story", "trust_category", "minimum_trust_level", "notes"]


# ---------------------------------------------------------------------------
# Phase 2 serializers
# ---------------------------------------------------------------------------


class GroupStoryProgressSerializer(serializers.ModelSerializer):
    """Serializer for GroupStoryProgress — per-GMTable progress pointer."""

    class Meta:
        model = GroupStoryProgress
        fields = [
            "id",
            "story",
            "gm_table",
            "current_episode",
            "started_at",
            "last_advanced_at",
            "is_active",
        ]
        read_only_fields = ["id", "started_at", "last_advanced_at"]

    def validate(self, attrs: Any) -> Any:
        """Enforce scope invariant via model's clean() — surfaces as 400."""
        # Build a temporary instance merging existing fields (for partial updates)
        # with the incoming attrs so clean() has a complete picture.
        existing: dict[str, Any] = {}
        if self.instance is not None:
            for field in ["story", "gm_table", "current_episode", "is_active"]:
                existing[field] = getattr(self.instance, field)
        merged = {**existing, **attrs}
        instance = GroupStoryProgress(**merged)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class GlobalStoryProgressSerializer(serializers.ModelSerializer):
    """Serializer for GlobalStoryProgress — singleton metaplot progress pointer."""

    class Meta:
        model = GlobalStoryProgress
        fields = [
            "id",
            "story",
            "current_episode",
            "started_at",
            "last_advanced_at",
            "is_active",
        ]
        read_only_fields = ["id", "started_at", "last_advanced_at"]

    def validate(self, attrs: Any) -> Any:
        """Enforce scope invariant via model's clean() — surfaces as 400."""
        existing: dict[str, Any] = {}
        if self.instance is not None:
            for field in ["story", "current_episode", "is_active"]:
                existing[field] = getattr(self.instance, field)
        merged = {**existing, **attrs}
        instance = GlobalStoryProgress(**merged)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class AggregateBeatContributionSerializer(serializers.ModelSerializer):
    """Read-only serializer for AggregateBeatContribution ledger rows."""

    class Meta:
        model = AggregateBeatContribution
        fields = [
            "id",
            "beat",
            "character_sheet",
            "roster_entry",
            "points",
            "era",
            "source_note",
            "recorded_at",
        ]
        read_only_fields = [
            "id",
            "beat",
            "character_sheet",
            "roster_entry",
            "points",
            "era",
            "source_note",
            "recorded_at",
        ]


class AssistantGMClaimSerializer(serializers.ModelSerializer):
    """Read-only serializer for AssistantGMClaim records."""

    class Meta:
        model = AssistantGMClaim
        fields = [
            "id",
            "beat",
            "assistant_gm",
            "status",
            "approved_by",
            "rejection_note",
            "framing_note",
            "requested_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "beat",
            "assistant_gm",
            "status",
            "approved_by",
            "rejection_note",
            "framing_note",
            "requested_at",
            "updated_at",
        ]


class SessionRequestSerializer(serializers.ModelSerializer):
    """Read-only serializer for SessionRequest records."""

    story_id = serializers.IntegerField(source="story.id", read_only=True)

    class Meta:
        model = SessionRequest
        fields = [
            "id",
            "episode",
            "story_id",
            "status",
            "event",
            "open_to_any_gm",
            "assigned_gm",
            "initiated_by_account",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "story_id"]


class BeatSerializer(serializers.ModelSerializer):
    """Full serializer for Beat including all Phase 2 predicate config fields."""

    class Meta:
        model = Beat
        fields = [
            "id",
            "episode",
            "predicate_type",
            "outcome",
            "visibility",
            "internal_description",
            "player_hint",
            "player_resolution_text",
            "order",
            # Predicate config fields
            "required_level",
            "required_achievement",
            "required_condition_template",
            "required_codex_entry",
            "referenced_story",
            "referenced_milestone_type",
            "referenced_chapter",
            "referenced_episode",
            "required_points",
            # AGM / scheduling
            "agm_eligible",
            "deadline",
            # Timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs: Any) -> Any:
        """Mirror Beat.clean() so predicate-type invariants surface as 400 responses."""
        # Build complete picture for clean(): existing values + incoming attrs.
        existing: dict[str, Any] = {}
        if self.instance is not None:
            for field_name in [
                "episode",
                "predicate_type",
                "outcome",
                "visibility",
                "internal_description",
                "player_hint",
                "player_resolution_text",
                "order",
                "required_level",
                "required_achievement",
                "required_condition_template",
                "required_codex_entry",
                "referenced_story",
                "referenced_milestone_type",
                "referenced_chapter",
                "referenced_episode",
                "required_points",
                "agm_eligible",
                "deadline",
            ]:
                existing[field_name] = getattr(self.instance, field_name)
        merged = {**existing, **attrs}
        temp = Beat(**merged)
        try:
            temp.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


# ---------------------------------------------------------------------------
# Wave 11: Action endpoint input serializers
# ---------------------------------------------------------------------------


def _resolve_progress(episode: "Episode", progress_id: int | None) -> "AnyStoryProgress | None":
    """Return the active progress record for the episode's story.

    If progress_id is supplied, fetch it directly from the scope-appropriate
    table and require it to belong to this story and be active.
    Otherwise dispatch on story.scope via get_active_progress_for_story.
    """
    from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415

    story = episode.chapter.story
    if progress_id is not None:
        match story.scope:
            case StoryScope.CHARACTER:
                return StoryProgress.objects.filter(
                    pk=progress_id, story=story, is_active=True
                ).first()
            case StoryScope.GROUP:
                return GroupStoryProgress.objects.filter(
                    pk=progress_id, story=story, is_active=True
                ).first()
            case StoryScope.GLOBAL:
                return GlobalStoryProgress.objects.filter(
                    pk=progress_id, story=story, is_active=True
                ).first()
            case _:
                return None
    return get_active_progress_for_story(story)


class ResolveEpisodeInputSerializer(serializers.Serializer):
    """Input for POST /api/episodes/{id}/resolve/.

    Context required:
        episode (Episode): the episode being resolved.

    Validates:
        - chosen_transition belongs to this episode (if provided).
        - An active progress record exists for the episode's story.

    Stores resolved ``progress`` and ``chosen_transition`` in validated_data.
    """

    progress_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    chosen_transition = serializers.PrimaryKeyRelatedField(
        queryset=Transition.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    gm_notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        episode: Episode = self.context["episode"]

        transition: Transition | None = attrs.get("chosen_transition")
        if transition is not None and transition.source_episode_id != episode.pk:
            raise serializers.ValidationError(
                {"chosen_transition": "Transition does not belong to this episode."}
            )

        progress = _resolve_progress(episode, attrs.get("progress_id"))
        if progress is None:
            raise serializers.ValidationError(
                {"non_field_errors": "No active progress record found for this episode's story."}
            )
        attrs["progress"] = progress
        return attrs


class EpisodeResolutionSerializer(serializers.ModelSerializer):
    """Read-only serializer for EpisodeResolution rows returned by the resolve action."""

    class Meta:
        model = EpisodeResolution
        fields = [
            "id",
            "episode",
            "character_sheet",
            "gm_table",
            "chosen_transition",
            "resolved_by",
            "era",
            "gm_notes",
            "resolved_at",
        ]
        read_only_fields = fields


class MarkBeatInputSerializer(serializers.Serializer):
    """Input for POST /api/beats/{id}/mark/.

    Context required:
        beat (Beat): the beat being marked.

    Validates:
        - beat.predicate_type == GM_MARKED.
        - An active progress record exists for the beat's story.

    Stores ``progress`` in validated_data.
    """

    outcome = serializers.ChoiceField(choices=BeatOutcome.choices)
    gm_notes = serializers.CharField(required=False, allow_blank=True, default="")
    progress_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        beat: Beat = self.context["beat"]

        if beat.predicate_type != BeatPredicateType.GM_MARKED:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "Only GM_MARKED beats can be resolved via the mark endpoint."
                    )
                }
            )

        progress = _resolve_progress(beat.episode, attrs.get("progress_id"))
        if progress is None:
            raise serializers.ValidationError(
                {"non_field_errors": "No active progress record found for this beat's story."}
            )
        attrs["progress"] = progress
        return attrs


class BeatCompletionSerializer(serializers.ModelSerializer):
    """Read-only serializer for BeatCompletion returned by the mark action."""

    class Meta:
        model = BeatCompletion
        fields = [
            "id",
            "beat",
            "character_sheet",
            "gm_table",
            "roster_entry",
            "outcome",
            "era",
            "gm_notes",
            "recorded_at",
        ]
        read_only_fields = fields


class ContributeBeatInputSerializer(serializers.Serializer):
    """Input for POST /api/beats/{id}/contribute/.

    Context required:
        beat (Beat): the beat being contributed to.
        request: the DRF request (for is_staff and user ownership check).

    Validates:
        - beat.predicate_type == AGGREGATE_THRESHOLD.
        - character_sheet exists (PrimaryKeyRelatedField).
        - The requesting user owns the character_sheet, or is staff.

    Stores ``character_sheet`` instance in validated_data.
    """

    character_sheet = serializers.PrimaryKeyRelatedField(
        queryset=CharacterSheet.objects.select_related("character"),
    )
    points = serializers.IntegerField(min_value=1)
    source_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        beat: Beat = self.context["beat"]
        request = self.context["request"]
        character_sheet = attrs["character_sheet"]

        if beat.predicate_type != BeatPredicateType.AGGREGATE_THRESHOLD:
            raise serializers.ValidationError(
                {"non_field_errors": "Only AGGREGATE_THRESHOLD beats accept contributions."}
            )

        if not request.user.is_staff:
            if character_sheet.character.db_account_id != request.user.pk:
                raise serializers.ValidationError(
                    {"character_sheet": "You may only contribute for your own character."}
                )

        return attrs


class RequestClaimInputSerializer(serializers.Serializer):
    """Input for POST /api/assistant-gm-claims/request/.

    Validates:
        - beat exists (PrimaryKeyRelatedField).
        - beat.agm_eligible is True.

    Stores ``beat`` instance in validated_data.
    """

    beat = serializers.PrimaryKeyRelatedField(queryset=Beat.objects.all())
    framing_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_beat(self, beat: Beat) -> Beat:
        if not beat.agm_eligible:
            msg = "This beat is not flagged as available for Assistant GM claims."
            raise serializers.ValidationError(msg)
        return beat


class ApproveClaimInputSerializer(serializers.Serializer):
    """Input for POST /api/assistant-gm-claims/{id}/approve/.

    Context required:
        claim (AssistantGMClaim): the claim being approved.

    Validates:
        - claim.status == REQUESTED.
    """

    framing_note = serializers.CharField(required=False, allow_null=True, default=None)

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        claim: AssistantGMClaim = self.context["claim"]
        if claim.status != AssistantClaimStatus.REQUESTED:
            raise serializers.ValidationError(
                {"non_field_errors": "Only REQUESTED claims can be approved."}
            )
        return attrs


class RejectClaimInputSerializer(serializers.Serializer):
    """Input for POST /api/assistant-gm-claims/{id}/reject/.

    Context required:
        claim (AssistantGMClaim): the claim being rejected.

    Validates:
        - claim.status == REQUESTED.
    """

    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        claim: AssistantGMClaim = self.context["claim"]
        if claim.status != AssistantClaimStatus.REQUESTED:
            raise serializers.ValidationError(
                {"non_field_errors": "Only REQUESTED claims can be rejected."}
            )
        return attrs


class CancelClaimInputSerializer(serializers.Serializer):
    """Input for POST /api/assistant-gm-claims/{id}/cancel/.

    Context required:
        claim (AssistantGMClaim): the claim being cancelled.

    Validates:
        - claim.status == REQUESTED (can only cancel before approval).
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        claim: AssistantGMClaim = self.context["claim"]
        if claim.status != AssistantClaimStatus.REQUESTED:
            raise serializers.ValidationError(
                {"non_field_errors": "Only REQUESTED claims can be cancelled."}
            )
        return attrs


class CompleteClaimInputSerializer(serializers.Serializer):
    """Input for POST /api/assistant-gm-claims/{id}/complete/.

    Context required:
        claim (AssistantGMClaim): the claim being completed.

    Validates:
        - claim.status == APPROVED (can only complete approved claims).
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        claim: AssistantGMClaim = self.context["claim"]
        if claim.status != AssistantClaimStatus.APPROVED:
            raise serializers.ValidationError(
                {"non_field_errors": "Only APPROVED claims can be completed."}
            )
        return attrs


class CancelSessionRequestInputSerializer(serializers.Serializer):
    """Input for POST /api/session-requests/{id}/cancel/.

    Context required:
        session_request (SessionRequest): the request being cancelled.

    Validates:
        - session_request.status == OPEN.
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        session_request: SessionRequest = self.context["session_request"]
        if session_request.status != SessionRequestStatus.OPEN:
            raise serializers.ValidationError(
                {"non_field_errors": "Only OPEN session requests can be cancelled."}
            )
        return attrs


class ResolveSessionRequestInputSerializer(serializers.Serializer):
    """Input for POST /api/session-requests/{id}/resolve/.

    Context required:
        session_request (SessionRequest): the request being resolved.

    Validates:
        - session_request.status == SCHEDULED.
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        session_request: SessionRequest = self.context["session_request"]
        if session_request.status != SessionRequestStatus.SCHEDULED:
            raise serializers.ValidationError(
                {"non_field_errors": "Only SCHEDULED session requests can be resolved."}
            )
        return attrs


class CreateEventFromSessionRequestInputSerializer(serializers.Serializer):
    """Input for POST /api/session-requests/{id}/create-event/.

    Context required:
        session_request (SessionRequest): the request being scheduled.

    Validates:
        - session_request.status == OPEN.
        - host_persona exists (PrimaryKeyRelatedField).

    Stores ``host_persona`` instance in validated_data.
    """

    name = serializers.CharField()
    scheduled_real_time = serializers.DateTimeField()
    host_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    location_id = serializers.IntegerField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    is_public = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        session_request: SessionRequest = self.context["session_request"]
        if session_request.status != SessionRequestStatus.OPEN:
            raise serializers.ValidationError(
                {"non_field_errors": "Only OPEN session requests can be scheduled."}
            )
        return attrs


class StoryLogSerializer(serializers.Serializer):
    """Renders a list of StoryLogBeatEntry / StoryLogEpisodeEntry dataclasses to JSON.

    Usage::

        entries = serialize_story_log(story=story, progress=progress, viewer_role=role)
        return Response(StoryLogSerializer(entries).data)

    Each entry is serialized per-type via isinstance dispatch. The ``entry_type``
    field distinguishes beat_completion from episode_resolution for frontend rendering.
    """

    entries = serializers.SerializerMethodField()

    def get_entries(self, log_entries: list) -> list[dict[str, Any]]:
        """Serialize each entry using per-type logic."""
        return [self._serialize_entry(e) for e in log_entries]

    def _serialize_entry(self, entry: StoryLogBeatEntry | StoryLogEpisodeEntry) -> dict[str, Any]:
        if isinstance(entry, StoryLogBeatEntry):
            return self._serialize_beat(entry)
        return self._serialize_episode(entry)

    def _serialize_beat(self, entry: StoryLogBeatEntry) -> dict[str, Any]:
        beat = entry.beat
        completion = entry.completion
        return {
            "entry_type": "beat_completion",
            "beat_id": beat.pk,
            "episode_id": beat.episode_id,
            "recorded_at": completion.recorded_at,
            "outcome": completion.outcome,
            "visibility": beat.visibility,
            "player_hint": entry.visible_player_hint,
            "player_resolution_text": entry.visible_player_resolution_text,
            "internal_description": entry.visible_internal_description,
            "gm_notes": entry.visible_gm_notes,
        }

    def _serialize_episode(self, entry: StoryLogEpisodeEntry) -> dict[str, Any]:
        resolution = entry.resolution
        trans = resolution.chosen_transition
        target = trans.target_episode if trans else None
        return {
            "entry_type": "episode_resolution",
            "episode_id": resolution.episode_id,
            "episode_title": resolution.episode.title,
            "resolved_at": resolution.resolved_at,
            "transition_id": trans.pk if trans else None,
            "target_episode_id": target.pk if target else None,
            "target_episode_title": target.title if target else None,
            "connection_type": trans.connection_type if trans else "",
            "connection_summary": trans.connection_summary if trans else "",
            "internal_notes": entry.visible_internal_notes,
        }

    def to_representation(self, instance: list) -> dict[str, Any]:
        """Accept the log entries list as the instance."""
        return {"entries": self.get_entries(instance)}
