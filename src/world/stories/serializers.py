from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.gm.constants import GMTableStatus
from world.gm.models import GMProfile, GMTable
from world.gm.serializers import GMProfileSerializer
from world.scenes.models import Persona
from world.societies.constants import RenownRisk
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    SessionRequestStatus,
    StakeResolutionColumn,
    StakeRewardSink,
    StoryGMOfferStatus,
    StoryMaturity,
    StoryScope,
    TransitionMode,
)
from world.stories.exceptions import MaturityPromotionError
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    BeatCompletion,
    Chapter,
    Episode,
    EpisodeProgressionRequirement,
    EpisodeResolution,
    EpisodeScene,
    Era,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    PlayerTrustLevel,
    RiskCalibration,
    SessionRequest,
    Stake,
    StakeContractActivation,
    StakeOutcome,
    StakeResolution,
    StakeRewardLine,
    StakeTemplate,
    Story,
    StoryFeedback,
    StoryGMOffer,
    StoryNote,
    StoryParticipation,
    StoryProgress,
    StoryTrustRequirement,
    TableBulletinPost,
    TableBulletinReply,
    Transition,
    TransitionRequiredOutcome,
    TrustCategory,
    TrustCategoryFeedbackRating,
)
from world.stories.types import (
    AnyStoryProgress,
    ConnectionType,
    StoryLogBeatEntry,
    StoryLogEpisodeEntry,
)

# ---------------------------------------------------------------------------
# Wave 6: Era lifecycle serializer
# ---------------------------------------------------------------------------


class EraSerializer(serializers.ModelSerializer):
    """Full serializer for Era — includes read-only story_count context field."""

    story_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Era
        fields = [
            "id",
            "name",
            "display_name",
            "season_number",
            "description",
            "status",
            "activated_at",
            "concluded_at",
            "created_at",
            "story_count",
        ]
        read_only_fields = ["id", "activated_at", "concluded_at", "created_at", "story_count"]

    def get_story_count(self, obj: Era) -> int:
        """Return the number of Story records whose created_in_era matches this era.

        Reads from the ``story_count`` annotation added by EraViewSet.queryset
        (``Count("stories_created_in_era")``). Falls back to a direct query only
        when the annotation is absent (e.g. in non-viewset serializer calls).
        """
        annotated = getattr(obj, "story_count", None)  # noqa: GETATTR_LITERAL
        if annotated is not None:
            return int(annotated)
        return Story.objects.filter(created_in_era=obj).count()


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


def _gm_text_gate(
    serializer: serializers.ModelSerializer,
    data: dict[str, object],
    story: Story,
    node_maturity: str,
) -> dict[str, object]:
    """Strip GM-only authoring text from ``data`` for player-tier viewers.

    ``data`` is typed ``dict[str, object]`` rather than a ``TypedDict``: it is
    the output of ``ModelSerializer.to_representation`` for *three different*
    serializers (Story / Chapter / Episode detail), each with a distinct
    ``Meta.fields`` set. No single closed ``TypedDict`` correctly types all
    three, and three hand-maintained TypedDicts mirroring DRF ``Meta.fields``
    would be the brittle denormalisation CLAUDE.md forbids. ``dict[str,
    object]`` is the precise, non-``Any`` type for "an open string-keyed map
    of already-serialised field values, from which GM-only keys are removed."

    Security contract (Task A3): for any viewer whose story-log role is NOT
    ``staff`` or ``lead_gm`` (player / no_access / no request in context), the
    serialized Story/Chapter/Episode MUST NOT expose ``description`` or
    ``consequences``, and ``summary`` MUST be ``""`` while ``node_maturity``
    is PITCH. Staff and Lead GM see the full representation. When there is no
    request in context we default to the most-restrictive (player) treatment
    so GM text never leaks by default.

    Privilege is decided by the single ``can_view_story_gm_text`` predicate
    (staff / Lead GM / owner). It is imported locally to match this module's
    existing convention for deferring ``world.stories.permissions`` imports
    (see ``BeatSerializer.get_can_mark``). Owner is folded into that one
    predicate rather than bolted on here as a separate check, and is NOT a
    role on ``classify_story_log_viewer_role`` because that classifier also
    drives ``serialize_story_log`` beat-visibility (owners must not gain
    SECRET-beat / GM-note access there).
    """
    from world.stories.permissions import can_view_story_gm_text  # noqa: PLC0415

    request = serializer.context.get("request")
    user = request.user if request is not None else None
    # No request in context → user is None → most-restrictive (strip), so
    # GM authoring text never leaks by default.
    if user is None or not can_view_story_gm_text(user, story):
        data.pop("description", None)
        # consequences is absent on the Story serializer — pop default is safe.
        data.pop("consequences", None)
        if node_maturity == StoryMaturity.PITCH:
            data["summary"] = ""
    return data


class StoryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for story detail views"""

    owners = serializers.StringRelatedField(many=True, read_only=True)
    active_gms = GMProfileSerializer(many=True, read_only=True)
    character_sheet = serializers.PrimaryKeyRelatedField(read_only=True)
    primary_table = serializers.PrimaryKeyRelatedField(read_only=True)
    chapters_count = serializers.IntegerField(source="chapters.count", read_only=True)
    trust_requirements = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id",
            "title",
            "description",
            "summary",
            "maturity",
            "status",
            "privacy",
            "scope",
            "owners",
            "active_gms",
            "trust_requirements",
            "character_sheet",
            "primary_table",
            "chapters_count",
            "created_at",
            "updated_at",
            "completed_at",
            "covenant",
        ]
        read_only_fields = [
            "id",
            "owners",
            "active_gms",
            "trust_requirements",
            "character_sheet",
            "primary_table",
            "chapters_count",
            "created_at",
            "updated_at",
            "completed_at",
        ]

    def get_trust_requirements(self, obj):
        """Get trust requirements for this story"""
        return obj.get_trust_requirements_summary()

    def to_representation(self, instance: Story) -> dict[str, object]:
        """Gate GM-only authoring text for player-tier viewers (Task A3)."""
        data = super().to_representation(instance)
        return _gm_text_gate(self, data, instance, str(instance.maturity))


class StoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating stories"""

    class Meta:
        model = Story
        # SECURITY (deliberate exception to the A3 _gm_text_gate): the create
        # serializers echo `description` / `summary` UNGATED. Safe today:
        # Story-create is staff-only and Chapter/Episode-create echo only the
        # requester's own just-submitted text — no third-party GM text is
        # disclosed. If a future change lets a non-staff user create a node
        # from someone else's draft, add gating here.
        fields = [
            "title",
            "description",
            "summary",
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
            "maturity",
            "consequences",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance: Chapter) -> dict[str, object]:
        """Gate GM-only authoring text for player-tier viewers (Task A3)."""
        data = super().to_representation(instance)
        return _gm_text_gate(self, data, instance.story, str(instance.maturity))


class ChapterCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chapters"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Chapter
        # SECURITY (deliberate exception to the A3 _gm_text_gate): the create
        # serializers echo `description` / `summary` UNGATED. Safe today:
        # Story-create is staff-only and Chapter/Episode-create echo only the
        # requester's own just-submitted text — no third-party GM text is
        # disclosed. If a future change lets a non-staff user create a node
        # from someone else's draft, add gating here.
        fields = ["story", "title", "description", "summary", "order"]

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
            "maturity",
            "resting_conclusion",
            "is_ending",
            "consequences",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance: Episode) -> dict[str, object]:
        """Gate GM-only authoring text for player-tier viewers (Task A3)."""
        data = super().to_representation(instance)
        return _gm_text_gate(self, data, instance.chapter.story, str(instance.maturity))


class EpisodeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating episodes"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Episode
        # SECURITY (deliberate exception to the A3 _gm_text_gate): the create
        # serializers echo `description` / `summary` / `resting_conclusion` /
        # `is_ending` UNGATED. Safe today: Story-create is staff-only and
        # Chapter/Episode-create echo only the requester's own just-submitted
        # text — no third-party GM text is disclosed. If a future change lets
        # a non-staff user create a node from someone else's draft, add
        # gating here.
        fields = [
            "chapter",
            "title",
            "description",
            "summary",
            "resting_conclusion",
            "is_ending",
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

    # Read-only context fields surfaced for the AGM opportunities browser.
    # These walk the episode__chapter__story FK chain; no extra queries thanks
    # to the select_related on BeatViewSet.queryset.
    episode_title = serializers.CharField(source="episode.title", read_only=True)
    chapter_title = serializers.CharField(source="episode.chapter.title", read_only=True)
    story_id = serializers.IntegerField(source="episode.chapter.story_id", read_only=True)
    story_title = serializers.CharField(source="episode.chapter.story.title", read_only=True)

    # Client-side gating: true when the requesting user may call POST /beats/{id}/mark/.
    # Delegates to CanMarkBeat.has_object_permission so the frontend can hide the Mark
    # button instead of rendering it optimistically and hitting a 403.
    can_mark = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Beat
        fields = [
            "id",
            "episode",
            "episode_title",
            "chapter_title",
            "story_id",
            "story_title",
            "predicate_type",
            "outcome",
            "visibility",
            "internal_description",
            "player_hint",
            "player_resolution_text",
            "order",
            "kind",
            "advances",
            "risk",
            "target_level",
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
            "required_society",
            "required_organization",
            "required_standing",
            # AGM / scheduling
            "agm_eligible",
            "deadline",
            # Consequence pools
            "success_consequences",
            "failure_consequences",
            "expired_consequences",
            # Timestamps
            "created_at",
            "updated_at",
            # Client-side permission gating
            "can_mark",
        ]
        read_only_fields = [
            "id",
            "episode_title",
            "chapter_title",
            "story_id",
            "story_title",
            "created_at",
            "updated_at",
            "can_mark",
        ]

    def get_can_mark(self, obj: Beat) -> bool:
        """Return True if the requesting user may mark this beat.

        Delegates to CanMarkBeat.has_object_permission.  The view arg is
        passed as None — CanMarkBeat does not use it.

        Requires the Beat queryset to select_related
        'episode__chapter__story__primary_table' to avoid N+1 on list endpoints.
        BeatViewSet.queryset already includes this chain.
        """
        from world.stories.permissions import CanMarkBeat  # noqa: PLC0415

        request = self.context.get("request")
        if request is None:
            return False
        return CanMarkBeat().has_object_permission(request, None, obj)  # type: ignore[arg-type]

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
                "required_society",
                "required_organization",
                "required_standing",
                "kind",
                "advances",
                "risk",
                "target_level",
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

        request = self.context.get("request")
        merged_risk = merged.get("risk") or RenownRisk.NONE
        user = request.user if request is not None else None
        # user.is_staff is safe on AccountDB and AnonymousUser; bool() guards None.
        is_staff = bool(user is not None and user.is_staff)

        # Ownership gate (#1770 PR1 review, fold-in): DRF never calls
        # has_object_permission on create, so IsBeatStoryOwnerOrStaff alone lets
        # any authenticated user POST a Beat onto anyone's episode. Enforce the
        # same ownership walk here via the shared predicate. On re-point (the
        # episode FK is being changed), both the old and new episode's story
        # must be owned by the requesting user.
        from world.stories.permissions import user_owns_episode_story  # noqa: PLC0415

        if not is_staff:
            episode = merged.get("episode")
            old_episode = self.instance.episode if self.instance is not None else None
            is_repoint = (
                old_episode is not None and episode is not None and old_episode.pk != episode.pk
            )
            owners_ok = episode is not None and user_owns_episode_story(cast(Any, user), episode)
            if is_repoint:
                owners_ok = owners_ok and user_owns_episode_story(
                    cast(Any, user), cast(Episode, old_episode)
                )
            if not owners_ok:
                msg = "You do not have permission to author a beat on this episode."
                raise serializers.ValidationError(msg)

        if merged_risk != RenownRisk.NONE and not is_staff:
            raise serializers.ValidationError(
                {
                    "risk": (
                        "Only staff may author beats above risk NONE. "
                        "Higher risk tiers unlock with GM trust level."
                    )
                }
            )
        return attrs


# ---------------------------------------------------------------------------
# Phase 4 Wave 9: Author editor serializers
# ---------------------------------------------------------------------------


class TransitionSerializer(serializers.ModelSerializer):
    """Full serializer for Transition — guarded episode graph edges.

    Read-only breadcrumb fields (source_episode_title, target_episode_title)
    provide context for the Wave 9 author editor without requiring extra lookups;
    they are served free via TransitionViewSet.queryset.select_related.
    """

    source_episode_title = serializers.CharField(source="source_episode.title", read_only=True)
    target_episode_title = serializers.SerializerMethodField()

    class Meta:
        model = Transition
        fields = [
            "id",
            "source_episode",
            "source_episode_title",
            "target_episode",
            "target_episode_title",
            "mode",
            "connection_type",
            "connection_summary",
            "order",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "source_episode_title",
            "target_episode_title",
            "created_at",
        ]

    def get_target_episode_title(self, obj: Transition) -> str | None:
        """Return target episode title, or None when target is null (frontier)."""
        if obj.target_episode_id is None:
            return None
        return obj.target_episode.title


class EpisodeProgressionRequirementSerializer(serializers.ModelSerializer):
    """Full serializer for EpisodeProgressionRequirement.

    Records a beat that must reach ``required_outcome`` before any outbound
    transition fires from the episode.
    """

    class Meta:
        model = EpisodeProgressionRequirement
        fields = [
            "id",
            "episode",
            "beat",
            "required_outcome",
        ]
        read_only_fields = ["id"]


class TransitionRequiredOutcomeSerializer(serializers.ModelSerializer):
    """Full serializer for TransitionRequiredOutcome.

    Records a beat outcome that must be satisfied for this specific transition
    to be eligible when the episode is resolved. Stake-level routing (#1770
    PR2): when ``stake`` is set the requirement routes on the stake's
    StakeOutcome column (``required_stake_column``) and ``required_outcome``
    must be blank — exactly one predicate shape per row; validation mirrors
    TransitionRequiredOutcome.clean().
    """

    class Meta:
        model = TransitionRequiredOutcome
        fields = [
            "id",
            "transition",
            "beat",
            "required_outcome",
            "stake",
            "required_stake_column",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: Any) -> Any:
        """Mirror the model clean(): exactly one predicate shape per row."""
        existing: dict[str, Any] = {}
        if self.instance is not None:
            for field_name in ("beat", "stake", "required_outcome", "required_stake_column"):
                existing[field_name] = getattr(self.instance, field_name)
        merged = {**existing, **attrs}

        stake = merged.get("stake")
        required_outcome = merged.get("required_outcome") or ""
        required_stake_column = merged.get("required_stake_column") or ""
        beat = merged.get("beat")

        if stake is not None:
            if not required_stake_column:
                raise serializers.ValidationError(
                    {"required_stake_column": "Required when stake is set."}
                )
            if required_outcome:
                msg = "Must be blank when stake is set (stake rows route on the stake column)."
                raise serializers.ValidationError({"required_outcome": msg})
            if beat is not None and stake.beat_id != beat.pk:
                raise serializers.ValidationError(
                    {"stake": "The stake must belong to this requirement's beat."}
                )
        else:
            if not required_outcome:
                raise serializers.ValidationError(
                    {"required_outcome": "Required when stake is not set."}
                )
            if required_stake_column:
                raise serializers.ValidationError(
                    {"required_stake_column": "Only allowed when stake is set."}
                )

        return attrs


# ---------------------------------------------------------------------------
# Wave 13: Atomic transition save serializer
# ---------------------------------------------------------------------------


class OutcomeInputSerializer(serializers.Serializer):
    """Nested routing-predicate row for SaveTransitionWithOutcomesInputSerializer.

    Carries both predicate shapes (#1770 PR2): a beat-level row
    (``required_outcome`` set, ``stake`` null) or a stake-level row (``stake``
    + ``required_stake_column`` set, ``required_outcome`` blank). Validation
    mirrors TransitionRequiredOutcome.clean() so the editor bulk-save
    round-trips stake-level routing instead of silently dropping it.
    """

    beat = serializers.PrimaryKeyRelatedField(queryset=Beat.objects.all())
    required_outcome = serializers.ChoiceField(
        choices=BeatOutcome.choices, required=False, allow_blank=True, default=""
    )
    stake = serializers.PrimaryKeyRelatedField(
        queryset=Stake.objects.all(), required=False, allow_null=True, default=None
    )
    required_stake_column = serializers.ChoiceField(
        choices=StakeResolutionColumn.choices, required=False, allow_blank=True, default=""
    )

    def validate_beat(self, beat: Beat) -> Beat:
        """Beat must belong to the source episode supplied via context."""
        source_episode: Episode | None = self.context.get("source_episode")
        if source_episode is not None and beat.episode_id != source_episode.pk:
            msg = "Beat does not belong to the source episode of this transition."
            raise serializers.ValidationError(msg)
        return beat

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        """Exactly one predicate shape, mirroring TransitionRequiredOutcome.clean()."""
        stake = attrs.get("stake")
        required_outcome = attrs.get("required_outcome") or ""
        required_stake_column = attrs.get("required_stake_column") or ""
        beat = attrs["beat"]

        if stake is not None:
            if not required_stake_column:
                raise serializers.ValidationError(
                    {"required_stake_column": "Required when stake is set."}
                )
            if required_outcome:
                msg = "Must be blank when stake is set (stake rows route on the stake column)."
                raise serializers.ValidationError({"required_outcome": msg})
            if stake.beat_id != beat.pk:
                raise serializers.ValidationError(
                    {"stake": "The stake must belong to this requirement's beat."}
                )
        else:
            if not required_outcome:
                raise serializers.ValidationError(
                    {"required_outcome": "Required when stake is not set."}
                )
            if required_stake_column:
                raise serializers.ValidationError(
                    {"required_stake_column": "Only allowed when stake is set."}
                )

        return attrs


class SaveTransitionWithOutcomesInputSerializer(serializers.Serializer):
    """Input for POST /api/transitions/save-with-outcomes/.

    Accepts the core Transition fields plus a nested list of routing predicates.
    Validates the whole payload before handing off to the service.

    Context required: none (the source_episode is read from transition.source_episode).
    """

    existing_id = serializers.PrimaryKeyRelatedField(
        queryset=Transition.objects.select_related("source_episode"),
        required=False,
        allow_null=True,
        default=None,
    )
    source_episode = serializers.PrimaryKeyRelatedField(queryset=Episode.objects.all())
    target_episode = serializers.PrimaryKeyRelatedField(
        queryset=Episode.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    mode = serializers.ChoiceField(choices=TransitionMode.choices)
    connection_type = serializers.ChoiceField(
        choices=ConnectionType.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    connection_summary = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    order = serializers.IntegerField(default=0, min_value=0)
    outcomes = OutcomeInputSerializer(many=True, required=False, default=list)

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        existing: Transition | None = attrs.get("existing_id")
        source_episode: Episode = attrs["source_episode"]
        target_episode: Episode | None = attrs.get("target_episode")

        # When updating, ensure the existing transition belongs to the same source episode.
        if existing is not None and existing.source_episode_id != source_episode.pk:
            msg = "existing_id transition does not belong to the given source_episode."
            raise serializers.ValidationError({"existing_id": msg})

        # target_episode must differ from source_episode (or be null for frontier).
        if target_episode is not None and target_episode.pk == source_episode.pk:
            msg = "target_episode must be different from source_episode."
            raise serializers.ValidationError({"target_episode": msg})

        # Lead GM permission check: only the Lead GM of the source episode's story
        # (or staff) may save transitions. This runs here because save-with-outcomes
        # is a detail=False action — no URL object exists for has_object_permission
        # to inspect. The view-level IsLeadGMOnTransitionStoryOrStaff.has_permission
        # only confirms a GMProfile exists; the authoritative check is here.
        request = self.context.get("request")
        if request is not None and not request.user.is_staff:
            from world.gm.models import GMProfile  # noqa: PLC0415

            story = source_episode.chapter.story
            try:
                gm_profile = request.user.gm_profile
            except GMProfile.DoesNotExist:
                msg = "Only GMs can save transitions."
                raise serializers.ValidationError({"non_field_errors": [msg]}) from None
            if not story.primary_table_id or story.primary_table.gm_id != gm_profile.pk:
                msg = "You can only save transitions on stories at your tables."
                raise serializers.ValidationError({"non_field_errors": [msg]})

        # Pass source_episode into nested outcome serializer context (belt-and-suspenders;
        # the child serializer receives context via the serializer chain).
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


class PromoteEpisodeInputSerializer(serializers.Serializer):
    """Input for POST /api/episodes/{id}/promote/.

    Context required:
        episode (Episode): the episode whose maturity is changing.

    Validates (Layer 2): mirrors ``promote_episode_maturity``'s PLOT-gate so a
    violation surfaces as a 400, not a service-raised 500. The gate only fires
    on an upward move *to* PLOT; lateral moves and demotions are never gated
    (non-linear sketchpad). The gate requires a non-empty resting_conclusion
    AND (an outbound transition OR is_ending).
    """

    _RANK = {
        StoryMaturity.PITCH: 0,
        StoryMaturity.OUTLINE: 1,
        StoryMaturity.PLOT: 2,
    }

    target = serializers.ChoiceField(choices=StoryMaturity.choices)

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        from world.stories.services.maturity import (  # noqa: PLC0415
            episode_meets_plot_gate,
        )

        episode: Episode = self.context["episode"]
        target: str = attrs["target"]

        current_rank = self._RANK[StoryMaturity(episode.maturity)]
        is_promotion = self._RANK[StoryMaturity(target)] > current_rank
        if target == StoryMaturity.PLOT and is_promotion and not episode_meets_plot_gate(episode):
            msg = MaturityPromotionError().user_message
            raise serializers.ValidationError({"target": msg})
        return attrs


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

    Stores ``progress``, ``participants``, and ``extra_participants`` in validated_data.
    """

    outcome = serializers.ChoiceField(choices=BeatOutcome.choices)
    gm_notes = serializers.CharField(required=False, allow_blank=True, default="")
    progress_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Persona.objects.all(),
        required=False,
        default=list,
        help_text=(
            "Required for GROUP-scope LEGEND_AWARD pools; ignored otherwise. "
            "List of Persona PKs who receive legend credit."
        ),
    )
    extra_participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Persona.objects.all(),
        required=False,
        default=list,
        help_text=(
            "CHARACTER scope only: additional personas to credit alongside the "
            "progress's primary persona."
        ),
    )

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


# ---------------------------------------------------------------------------
# Wave 2: Table assignment input serializers
# ---------------------------------------------------------------------------


class AssignStoryToTableInputSerializer(serializers.Serializer):
    """Input for POST /api/stories/{id}/assign-to-table/.

    Validates that the requesting user is the Lead GM of the destination table
    (or staff). The story-side permission (can this story be assigned?) is
    handled by the view's get_object() / queryset scoping.
    """

    table = serializers.PrimaryKeyRelatedField(
        queryset=GMTable.objects.filter(status=GMTableStatus.ACTIVE),
    )

    def validate_table(self, table: GMTable) -> GMTable:
        """Verify the requesting user can assign stories to this table."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context is required."
            raise serializers.ValidationError(msg)
        user = request.user
        if user.is_staff:
            return table
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = user.gm_profile
        except GMProfile.DoesNotExist:
            msg = "You must be a GM to assign stories to a table."
            raise serializers.ValidationError(msg) from None
        if table.gm_id != gm_profile.pk:
            msg = "You can only assign stories to your own table."
            raise serializers.ValidationError(msg)
        return table


class AssignStoryInputSerializer(serializers.Serializer):
    """Input for POST /api/stories/{id}/assign-to-scope/ (Task B2).

    Lifts a Story out of UNASSIGNED scope: picks the scope and the matching
    target so a progress record can be created.

    Layer 2 invariant — scope <-> target:
        - CHARACTER requires ``character_sheet`` and forbids ``gm_table``.
        - GROUP requires ``gm_table`` and forbids ``character_sheet``.
        - GLOBAL forbids both targets.
        - UNASSIGNED is not an acceptable input scope (you cannot assign a
          story *to* unassigned); the ChoiceField excludes it so it 400s.
    """

    scope = serializers.ChoiceField(
        choices=[
            (choice.value, choice.label) for choice in StoryScope if choice != StoryScope.UNASSIGNED
        ],
    )
    character_sheet = serializers.PrimaryKeyRelatedField(
        queryset=CharacterSheet.objects.all(),
        required=False,
        allow_null=True,
    )
    gm_table = serializers.PrimaryKeyRelatedField(
        queryset=GMTable.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        """Enforce the scope <-> target invariant.

        Precondition: the target story must currently be UNASSIGNED. The
        assign contract is "lift a story OUT of UNASSIGNED"; re-assigning an
        already-scoped story would either 500 (duplicate progress record) or
        silently corrupt data (scope change with a stale character_sheet and
        an orphan progress row), so it is rejected as invalid input here.
        """
        story = self.context["story"]
        if story.scope != StoryScope.UNASSIGNED:
            msg = "This story is already assigned to a scope and cannot be re-assigned."
            raise serializers.ValidationError({"scope": msg})

        self._validate_scope_target_invariant(attrs)
        return attrs

    @staticmethod
    def _validate_scope_target_invariant(attrs: Any) -> None:
        """Enforce the scope <-> target invariant (CHARACTER/GROUP/GLOBAL)."""
        scope = attrs["scope"]
        character_sheet = attrs.get("character_sheet")
        gm_table = attrs.get("gm_table")

        if scope == StoryScope.CHARACTER:
            if character_sheet is None:
                msg = "CHARACTER scope requires a character_sheet."
                raise serializers.ValidationError({"character_sheet": msg})
            if gm_table is not None:
                msg = "CHARACTER scope does not accept a gm_table."
                raise serializers.ValidationError({"gm_table": msg})
        elif scope == StoryScope.GROUP:
            if gm_table is None:
                msg = "GROUP scope requires a gm_table."
                raise serializers.ValidationError({"gm_table": msg})
            if character_sheet is not None:
                msg = "GROUP scope does not accept a character_sheet."
                raise serializers.ValidationError({"character_sheet": msg})
        elif scope == StoryScope.GLOBAL:
            if character_sheet is not None:
                msg = "GLOBAL scope does not accept a character_sheet."
                raise serializers.ValidationError({"character_sheet": msg})
            if gm_table is not None:
                msg = "GLOBAL scope does not accept a gm_table."
                raise serializers.ValidationError({"gm_table": msg})


# ---------------------------------------------------------------------------
# Wave 3: StoryGMOffer serializers
# ---------------------------------------------------------------------------


class StoryGMOfferSerializer(serializers.ModelSerializer):
    """Read serializer for StoryGMOffer records."""

    class Meta:
        model = StoryGMOffer
        fields = [
            "id",
            "story",
            "offered_to",
            "offered_by_account",
            "status",
            "message",
            "response_note",
            "created_at",
            "responded_at",
            "updated_at",
        ]
        read_only_fields = fields


class OfferStoryToGMInputSerializer(serializers.Serializer):
    """Input for POST /api/stories/{id}/offer-to-gm/.

    Context required:
        story (Story): the story being offered (resolved by get_object()).
        request: DRF request (for user identity + staff check).

    Validates:
        - story.scope == CHARACTER (service will catch this, but serializer validates first)
        - story.primary_table is None
        - gm_profile_id points to an existing GMProfile

    Stores ``offered_to`` (GMProfile) in validated_data.
    """

    gm_profile_id = serializers.IntegerField()
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_gm_profile_id(self, value: int) -> int:
        from world.gm.models import GMProfile  # noqa: PLC0415

        if not GMProfile.objects.filter(pk=value).exists():
            msg = "No GM with that profile ID exists."
            raise serializers.ValidationError(msg)
        return value

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        story: Story = self.context["story"]
        request = self.context["request"]

        # Permission: only the character-scope owner (or staff) can offer this story.
        if not request.user.is_staff:
            if story.scope != StoryScope.CHARACTER or story.character_sheet_id is None:
                msg = "Only CHARACTER-scope stories with an owner can be offered to a GM."
                raise serializers.ValidationError({"non_field_errors": msg})
            if story.character_sheet.character.db_account_id != request.user.pk:
                msg = "You can only offer your own story."
                raise serializers.ValidationError({"non_field_errors": msg})

        if story.scope != StoryScope.CHARACTER:
            msg = "Only CHARACTER-scope stories support GM offers."
            raise serializers.ValidationError({"non_field_errors": msg})
        if story.primary_table_id is not None:
            msg = "Withdraw from the current GM's table before offering this story to another GM."
            raise serializers.ValidationError({"non_field_errors": msg})

        from world.gm.models import GMProfile  # noqa: PLC0415

        attrs["offered_to"] = GMProfile.objects.get(pk=attrs["gm_profile_id"])
        return attrs


class AcceptOfferInputSerializer(serializers.Serializer):
    """Input for POST /api/story-gm-offers/{id}/accept/.

    Context required:
        offer (StoryGMOffer): the offer being accepted.

    Validates:
        - offer.status == PENDING
    """

    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        offer: StoryGMOffer = self.context["offer"]
        if offer.status != StoryGMOfferStatus.PENDING:
            msg = "Only PENDING offers can be accepted."
            raise serializers.ValidationError({"non_field_errors": msg})
        return attrs


class DeclineOfferInputSerializer(serializers.Serializer):
    """Input for POST /api/story-gm-offers/{id}/decline/.

    Context required:
        offer (StoryGMOffer): the offer being declined.

    Validates:
        - offer.status == PENDING
    """

    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        offer: StoryGMOffer = self.context["offer"]
        if offer.status != StoryGMOfferStatus.PENDING:
            msg = "Only PENDING offers can be declined."
            raise serializers.ValidationError({"non_field_errors": msg})
        return attrs


class WithdrawOfferInputSerializer(serializers.Serializer):
    """Input for POST /api/story-gm-offers/{id}/withdraw/.

    Context required:
        offer (StoryGMOffer): the offer being withdrawn.

    Validates:
        - offer.status == PENDING
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        offer: StoryGMOffer = self.context["offer"]
        if offer.status != StoryGMOfferStatus.PENDING:
            msg = "Only PENDING offers can be withdrawn."
            raise serializers.ValidationError({"non_field_errors": msg})
        return attrs


# ---------------------------------------------------------------------------
# Wave 10: TableBulletin serializers
# ---------------------------------------------------------------------------


class TableBulletinReplySerializer(serializers.ModelSerializer):
    """Read serializer for TableBulletinReply."""

    class Meta:
        model = TableBulletinReply
        fields = [
            "id",
            "post",
            "author_persona",
            "body",
            "created_at",
        ]
        read_only_fields = ["id", "post", "author_persona", "created_at"]


class TableBulletinPostSerializer(serializers.ModelSerializer):
    """Read serializer for TableBulletinPost — includes nested reply list.

    Replies are read from ``replies_cached`` (set by the ViewSet's
    Prefetch to_attr) when available, falling back to the reverse manager.
    """

    replies = serializers.SerializerMethodField()

    class Meta:
        model = TableBulletinPost
        fields = [
            "id",
            "table",
            "story",
            "author_persona",
            "title",
            "body",
            "allow_replies",
            "created_at",
            "updated_at",
            "replies",
        ]
        read_only_fields = [
            "id",
            "table",
            "story",
            "author_persona",
            "created_at",
            "updated_at",
            "replies",
        ]

    def get_replies(self, obj: Any) -> list[Any]:
        """Return cached replies (from Prefetch to_attr) or query the DB."""
        reply_list = getattr(obj, "replies_cached", None)  # noqa: GETATTR_LITERAL
        if reply_list is None:
            reply_list = list(obj.replies.select_related("author_persona").all())
        return TableBulletinReplySerializer(reply_list, many=True).data


class CreateBulletinPostInputSerializer(serializers.Serializer):
    """Input for POST /api/table-bulletin-posts/.

    Validates:
    - ``table`` exists and user is its Lead GM (or staff)
    - ``story`` (if set) belongs to ``table`` (story.primary_table == table)
    - ``author_persona`` belongs to the requesting user's account

    Stores validated model instances in validated_data.
    """

    table = serializers.PrimaryKeyRelatedField(queryset=GMTable.objects.all())
    story = serializers.PrimaryKeyRelatedField(
        queryset=Story.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    author_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    allow_replies = serializers.BooleanField(required=False, default=True)

    def validate_table(self, table: GMTable) -> GMTable:
        """User must be the Lead GM of the table (or staff)."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context is required."
            raise serializers.ValidationError(msg)
        if getattr(request.user, "is_staff", False):  # noqa: GETATTR_LITERAL
            return table
        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            msg = "You must be a GM to post bulletins."
            raise serializers.ValidationError(msg) from None
        if table.gm_id != gm_profile.pk:
            msg = "You can only post bulletins to your own table."
            raise serializers.ValidationError(msg)
        return table

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        """Validate that story (if set) belongs to the specified table."""
        table: GMTable = attrs["table"]
        story: Story | None = attrs.get("story")
        if story is not None and story.primary_table_id != table.pk:
            msg = "The selected story is not assigned to this table."
            raise serializers.ValidationError({"story": msg})
        return attrs


class UpdateBulletinPostInputSerializer(serializers.Serializer):
    """Input for PATCH /api/table-bulletin-posts/{id}/.

    Only the post author (Lead GM of the table) or staff may edit.
    No field is required; all are optional.
    """

    title = serializers.CharField(max_length=200, required=False)
    body = serializers.CharField(required=False)
    allow_replies = serializers.BooleanField(required=False)


class CreateBulletinReplyInputSerializer(serializers.Serializer):
    """Input for POST /api/table-bulletin-replies/.

    Validates:
    - ``post`` exists
    - post.allow_replies=True (or user is staff)
    - requesting user has read access to the post
    - ``author_persona`` belongs to the requesting user's account

    Stores validated model instances in validated_data.
    """

    post = serializers.PrimaryKeyRelatedField(queryset=TableBulletinPost.objects.all())
    author_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    body = serializers.CharField()

    def validate_post(self, post: TableBulletinPost) -> TableBulletinPost:
        """Verify replies are enabled on this post (staff bypass)."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context is required."
            raise serializers.ValidationError(msg)
        if not post.allow_replies and not request.user.is_staff:
            msg = "Replies are disabled on this post."
            raise serializers.ValidationError(msg)
        # Also check that the user can read the post.
        from world.stories.permissions import _user_can_read_bulletin_post  # noqa: PLC0415

        if not _user_can_read_bulletin_post(request.user, post):
            msg = "You do not have access to this bulletin post."
            raise serializers.ValidationError(msg)
        return post


class UpdateBulletinReplyInputSerializer(serializers.Serializer):
    """Input for PATCH /api/table-bulletin-replies/{id}/.

    Only the reply author or staff may edit.
    """

    body = serializers.CharField()


# ---------------------------------------------------------------------------
# StoryNote serializer (append-only OOC authorial memory)
# ---------------------------------------------------------------------------


class StoryNoteSerializer(serializers.ModelSerializer):
    """List + create serializer for StoryNote (append-only, GM/staff/owner only).

    ``author_account`` is set from the requesting account (Evennia AccountDB)
    in ``create()`` — it is never accepted from client input.
    """

    story = serializers.PrimaryKeyRelatedField(queryset=Story.objects.all())

    class Meta:
        model = StoryNote
        fields = ["id", "story", "author_account", "body", "created_at"]
        read_only_fields = ["id", "author_account", "created_at"]

    def validate_story(self, story: Story) -> Story:
        """Create-scope (Layer 2): requester must be able to access the story.

        Mirrors the object-level access predicate used by the permission
        class and queryset (staff, story owner, active GM, or Lead GM of the
        story's primary table).
        """
        from world.stories.permissions import (  # noqa: PLC0415
            _user_can_access_story_notes,
        )

        user = self.context["request"].user
        if not _user_can_access_story_notes(user, story):
            msg = "Only staff, the story owner, or an active GM may add notes to this story."
            raise serializers.ValidationError(msg)
        return story

    def validate_body(self, value: str) -> str:
        """Reject blank/whitespace-only note bodies."""
        if not value.strip():
            msg = "Note body cannot be blank."
            raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data: dict[str, Any]) -> StoryNote:
        """Stamp author_account from the requesting account before saving."""
        request = self.context["request"]
        validated_data["author_account"] = request.user
        return cast(Any, StoryNote).objects.create(**validated_data)


# ---------------------------------------------------------------------------
# #1770 PR1: Stakes-contract engine serializers
# ---------------------------------------------------------------------------


class RiskCalibrationSerializer(serializers.ModelSerializer):
    """Full serializer for RiskCalibration (#1770 pillar 5).

    Staff-write / authenticated-read — enforced by IsStaffOrReadOnly on the
    ViewSet, not here.
    """

    class Meta:
        model = RiskCalibration
        fields = [
            "id",
            "risk",
            "severity_floor_total",
            "severity_ceiling",
            "max_fuse_hops",
            "reward_floor",
            "reward_ceiling",
        ]
        read_only_fields = ["id"]


class StakeTemplateSerializer(serializers.ModelSerializer):
    """Full serializer for StakeTemplate (#1770 pillar 5, menu-first catalog).

    Staff-write / authenticated-read — enforced by IsStaffOrReadOnly on the
    ViewSet, not here.
    """

    class Meta:
        model = StakeTemplate
        fields = [
            "id",
            "name",
            "subject_kind",
            "severity",
            "min_risk",
            "max_risk",
            "player_summary_template",
            "description",
            "is_active",
        ]
        read_only_fields = ["id"]


def _check_stake_beat_lock(beat: Any, old_beat: Any, is_repoint: bool) -> None:
    """Reject the write if the effective beat (or, on re-point, the old beat) is locked.

    #1770 PR1 review: re-pointing a Stake to/from a locked beat must be rejected
    either way, not just checked against the incoming beat.
    """
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    beats_to_check = [beat] if not is_repoint else [beat, old_beat]
    for candidate in beats_to_check:
        if candidate is not None and get_open_activation(candidate) is not None:
            msg = "This beat's stakes contract is locked by an open activation."
            raise serializers.ValidationError(msg)


def _check_stake_beat_ownership(
    user: Any, is_staff: bool, beat: Any, old_beat: Any, is_repoint: bool
) -> None:
    """Reject the write unless staff or the requesting user owns the beat's story.

    #1770 PR1 review: DRF never calls has_object_permission on create, so
    IsStakeBeatStoryOwnerOrStaff alone lets any authenticated user POST a Stake
    onto anyone's beat. On re-point, both the old and new beat's story must be
    owned by the requesting user.
    """
    from world.stories.permissions import user_owns_beat_story  # noqa: PLC0415

    if is_staff:
        return
    owners_ok = beat is not None and user_owns_beat_story(user, beat)
    if is_repoint:
        owners_ok = owners_ok and user_owns_beat_story(user, old_beat)
    if not owners_ok:
        msg = "You do not have permission to author a stake on this beat."
        raise serializers.ValidationError(msg)


class StakeOutcomeSerializer(serializers.ModelSerializer):
    """Read-only serializer for StakeOutcome — the per-stake resolution audit
    row (#1770 PR2). Written only by the resolution services (machine grading
    or the constrained-pick endpoint), never via direct CRUD.
    """

    class Meta:
        model = StakeOutcome
        fields = [
            "id",
            "stake",
            "activation",
            "resolution",
            "column",
            "method",
            "resolved_by",
            "gm_notes",
            "created_at",
        ]
        read_only_fields = fields


class ResolveStakeInputSerializer(serializers.Serializer):
    """Input for POST /api/stakes/{id}/resolve/ — the GM constrained pick.

    Context required:
        stake (Stake): the stake being resolved.

    Validates:
        - The stake has no StakeOutcome yet (a pick is final; idempotent API).
        - The chosen column is among the stake's AUTHORED resolutions — the
          pick is constrained, never free composition.
        - The stake's beat has completed (outcome != UNSATISFIED).

    ``participants`` / ``extra_participants`` — same semantics as
    MarkBeatInputSerializer: GROUP-scope LEGEND_AWARD branch pools need an
    explicit participant list; CHARACTER scope may credit extras alongside
    the progress's primary persona.
    """

    column = serializers.ChoiceField(choices=StakeResolutionColumn.choices)
    outcome_key = serializers.CharField(required=False, allow_blank=True, default="")
    gm_notes = serializers.CharField(required=False, allow_blank=True, default="")
    participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Persona.objects.all(),
        required=False,
        default=list,
        help_text=(
            "GROUP scope: explicit Persona PKs credited by the branch's pool "
            "(required for LEGEND_AWARD pools) and affection writer."
        ),
    )
    extra_participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Persona.objects.all(),
        required=False,
        default=list,
        help_text=(
            "CHARACTER scope only: additional personas to credit alongside the "
            "progress's primary persona."
        ),
    )

    def validate(self, attrs: Any) -> Any:
        stake = self.context["stake"]

        # Query the table directly — the view's prefetched `stake.outcomes`
        # cache on the idmapper-shared instance can be stale within a request
        # cycle, and this check must be point-in-time correct.
        if StakeOutcome.objects.filter(stake=stake).exists():
            raise serializers.ValidationError(
                {"non_field_errors": "This stake has already been resolved."}
            )

        authored = set(stake.resolutions.values_list("column", "outcome_key"))
        pick = (attrs["column"], attrs.get("outcome_key", ""))
        if pick not in authored:
            branches = sorted(authored) or "none authored"
            raise serializers.ValidationError(
                {
                    "column": (
                        "A GM pick is constrained to the stake's authored "
                        f"(column, outcome_key) branches ({branches}) — never free "
                        "composition. Author the branch first."
                    )
                }
            )

        if stake.beat.outcome == BeatOutcome.UNSATISFIED:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "The stake's beat has not completed; stakes resolve at or "
                        "after beat completion."
                    )
                }
            )

        return attrs


class StakeSerializer(serializers.ModelSerializer):
    """Full serializer for Stake (#1770 pillar 1).

    Template-set path denormalizes subject_kind/severity from the template
    (so a later template retune never rewrites live contracts) and validates
    the beat's declared risk falls within the template's [min_risk, max_risk]
    band (by risk_index). The template-null (CUSTOM) path is staff-gated,
    mirroring BeatSerializer.validate's risk staff gate verbatim in style.
    Any write (create or update) is rejected while the beat carries an open
    StakeContractActivation — the lock (#1770 pillar 8).
    ``outcomes`` (PR2) exposes the read-only resolution audit rows.
    """

    outcomes = StakeOutcomeSerializer(many=True, read_only=True)

    class Meta:
        model = Stake
        fields = [
            "id",
            "beat",
            "template",
            "subject_kind",
            "severity",
            "subject_sheet",
            "subject_item",
            "subject_society",
            "subject_organization",
            "subject_label",
            "player_summary",
            "outcomes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "subject_kind": {"required": False},
            "severity": {"required": False},
        }

    def validate(self, attrs: Any) -> Any:
        """Ownership gate, two-sided lock check, template defaulting/banding, custom-stake gate."""
        from world.stories.services.stakes import risk_index  # noqa: PLC0415

        existing: dict[str, Any] = {}
        if self.instance is not None:
            for field_name in ("beat", "template", "subject_kind", "severity"):
                existing[field_name] = getattr(self.instance, field_name)
        merged = {**existing, **attrs}

        beat = merged.get("beat")
        old_beat = self.instance.beat if self.instance is not None else None
        is_repoint = old_beat is not None and beat is not None and old_beat.pk != beat.pk

        request = self.context.get("request")
        user = request.user if request is not None else None
        # user.is_staff is safe on AccountDB and AnonymousUser; bool() guards None.
        is_staff = bool(user is not None and user.is_staff)

        # Ownership before lock (#1770 review): a non-owner probing a foreign
        # beat must get the permission error, never learn the lock state.
        _check_stake_beat_ownership(user, is_staff, beat, old_beat, is_repoint)

        _check_stake_beat_lock(beat, old_beat, is_repoint)

        template = merged.get("template")

        if template is not None:
            if beat is not None:
                beat_idx = risk_index(beat.risk)
                band_lo = risk_index(template.min_risk)
                band_hi = risk_index(template.max_risk)
                if not band_lo <= beat_idx <= band_hi:
                    raise serializers.ValidationError(
                        {
                            "template": (
                                f"Template {template.name!r} is banded for risk "
                                f"{template.min_risk}-{template.max_risk}; "
                                f"this beat is declared at {beat.risk}."
                            )
                        }
                    )
            attrs.setdefault("subject_kind", template.subject_kind)
            attrs.setdefault("severity", template.severity)
        else:
            if not is_staff:
                raise serializers.ValidationError(
                    {
                        "template": (
                            "Only staff may author custom stakes (template=null). "
                            "Use a StakeTemplate instead."
                        )
                    }
                )
            if merged.get("subject_kind") is None:
                raise serializers.ValidationError(
                    {"subject_kind": "subject_kind is required when template is null."}
                )
            if merged.get("severity") is None:
                raise serializers.ValidationError(
                    {"severity": "severity is required when template is null."}
                )

        self._check_boundaries(beat, attrs)

        return attrs

    def _candidate_stake(self, beat: Any, attrs: Any) -> Stake:
        """An unsaved Stake carrying this write's effective field values.

        For updates, fields absent from ``attrs`` fall back to the instance,
        so the screen sees the row as it would exist after the write.
        """
        field_names = (
            "template",
            "subject_kind",
            "severity",
            "subject_sheet",
            "subject_item",
            "subject_society",
            "subject_organization",
            "subject_label",
            "player_summary",
        )
        values = {}
        for name in field_names:
            if name in attrs:
                values[name] = attrs[name]
            elif self.instance is not None:
                values[name] = getattr(self.instance, name)
        return Stake(beat=beat, **values)

    def _check_boundaries(self, beat: Any, attrs: Any) -> None:
        """Authoring-time boundary screen (#1770 pillar 10).

        Screens the beat's existing stakes PLUS the candidate write (an
        unsaved Stake built from the effective attrs), so the screen sees the
        contract as it would exist after this write. Participants are unknown
        at authoring, so the sheet list is empty — this becomes a real screen
        when the boundary registry (#1771) ships; today's stub never blocks.
        A pending sign-off requirement blocks like a denial (#1771 forward
        compatibility). The failure message is deliberately generic: a
        player's boundary is never surfaced (ADR-0033).
        """
        from world.stories.services.boundaries import check_stake_boundaries  # noqa: PLC0415

        existing = []
        if beat is not None:
            existing_qs = beat.stakes.all()
            if self.instance is not None:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            existing = list(existing_qs)
        report = check_stake_boundaries([*existing, self._candidate_stake(beat, attrs)], [])
        if not report.cleared:
            msg = "These stakes could not be authored against a player boundary."
            raise serializers.ValidationError(msg)


class StakeRewardLineSerializer(serializers.ModelSerializer):
    """Full serializer for StakeRewardLine (#1770 PR3 — the contract's win side).

    Mirrors StakeResolutionSerializer's gates one hop deeper: the ownership
    walk via resolution.stake.beat (create-path enforcement), the two-sided
    open-activation lock, the completed-beat refusal, the WIN-column-only
    rule, and the sink/resonance shape rule (resonance required iff
    sink=RESONANCE; amount >= 1 rides the model validator).
    Banding against the tier's reward floor/ceiling is deliberately NOT
    rejected here — out-of-band rewards make the contract UNREADY instead
    (pillar 7 auto-downgrade); the payout re-checks the band at pay time.
    """

    class Meta:
        model = StakeRewardLine
        fields = [
            "id",
            "resolution",
            "sink",
            "amount",
            "resonance",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: Any) -> Any:
        """Ownership gate + two-sided lock check via the (possibly re-pointed) resolution."""
        from world.stories.permissions import user_owns_beat_story  # noqa: PLC0415
        from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

        old_resolution = self.instance.resolution if self.instance is not None else None
        resolution = attrs.get("resolution") or old_resolution
        is_repoint = (
            old_resolution is not None
            and resolution is not None
            and old_resolution.pk != resolution.pk
        )

        request = self.context.get("request")
        user = request.user if request is not None else None
        # user.is_staff is safe on AccountDB and AnonymousUser; bool() guards None.
        is_staff = bool(user is not None and user.is_staff)

        # Ownership gate: DRF never calls has_object_permission on create, so
        # IsStakeRewardLineBeatStoryOwnerOrStaff alone would let any
        # authenticated user POST a reward line onto anyone's resolution.
        # Ownership before lock — a non-owner probing a foreign resolution
        # must get the permission error, never learn the lock state.
        if not is_staff:
            owners_ok = resolution is not None and user_owns_beat_story(
                cast(Any, user), resolution.stake.beat
            )
            if is_repoint:
                owners_ok = owners_ok and user_owns_beat_story(
                    cast(Any, user), old_resolution.stake.beat
                )
            if not owners_ok:
                msg = "You do not have permission to author a reward line on this resolution."
                raise serializers.ValidationError(msg)

        # Lock check: re-pointing to/from a resolution whose beat is locked is
        # rejected either way — check both sides when re-pointing.
        # Completed-beat check (#1770 PR3 review): once the completion tail
        # closes the activation (with stakes possibly pending a GM pick), the
        # open-activation lock no longer bites — without this check reward
        # lines could be re-authored after the contract ran and pay out on
        # the stale activation's readiness verdict.
        resolutions_to_check = [resolution] if not is_repoint else [resolution, old_resolution]
        for candidate in resolutions_to_check:
            if candidate is not None and get_open_activation(candidate.stake.beat) is not None:
                msg = "This beat's stakes contract is locked by an open activation."
                raise serializers.ValidationError(msg)
            if candidate is not None and candidate.stake.beat.outcome != BeatOutcome.UNSATISFIED:
                msg = "This beat has completed; its stakes contract can no longer be edited."
                raise serializers.ValidationError(msg)

        # WIN-column only (#1770 PR3 review): a "consolation" line on a
        # LOSS/WITHDRAWAL branch would be silently inert — refuse it.
        if resolution is not None and resolution.column != StakeResolutionColumn.WIN:
            raise serializers.ValidationError(
                {"resolution": "Reward lines only attach to WIN-column resolutions."}
            )

        self._validate_sink_shape(attrs)

        return attrs

    def _validate_sink_shape(self, attrs: Any) -> None:
        """Resonance required iff sink=RESONANCE (mirrors StakeRewardLine.clean)."""

        def merged(field_name: str, default: Any) -> Any:
            if field_name in attrs:
                return attrs[field_name]
            if self.instance is not None:
                return getattr(self.instance, field_name)
            return default

        sink = merged("sink", default="")
        resonance = merged("resonance", default=None)
        if sink == StakeRewardSink.RESONANCE and resonance is None:
            raise serializers.ValidationError({"resonance": "Required when sink is RESONANCE."})
        if sink != StakeRewardSink.RESONANCE and resonance is not None:
            raise serializers.ValidationError({"resonance": "Only allowed when sink is RESONANCE."})


class StakeResolutionSerializer(serializers.ModelSerializer):
    """Full serializer for StakeResolution (#1770 pillar 1).

    PR2 adds the writer-payload fields and the pillar-12 no-fiat guard:
    sets_subject_lifecycle is only legal for NPC_FATE stakes whose subject
    sheet is not player-held; item forfeiture and affection deltas must match
    the stake's subject kind. No column-ordering/escalation validation (the
    fuse walk measures reachability, not monotonicity).
    ``reward_lines`` (PR3) exposes the branch's authored win-reward payouts
    read-only; they are written via the stake-reward-lines endpoint.
    """

    reward_lines = StakeRewardLineSerializer(many=True, read_only=True)

    class Meta:
        model = StakeResolution
        fields = [
            "id",
            "stake",
            "column",
            "outcome_key",
            "consequence_pool",
            "escalates_to_risk",
            "narrative_summary",
            "forfeits_subject_item",
            "subject_standing_delta",
            "sets_subject_lifecycle",
            "machine_match_lifecycle_state",
            "reward_lines",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: Any) -> Any:
        """Ownership gate + two-sided lock check via the (possibly re-pointed) stake."""
        from world.stories.permissions import user_owns_beat_story  # noqa: PLC0415
        from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

        old_stake = self.instance.stake if self.instance is not None else None
        stake = attrs.get("stake") or old_stake
        is_repoint = old_stake is not None and stake is not None and old_stake.pk != stake.pk

        request = self.context.get("request")
        user = request.user if request is not None else None
        # user.is_staff is safe on AccountDB and AnonymousUser; bool() guards None.
        is_staff = bool(user is not None and user.is_staff)

        # Ownership gate (#1770 PR1 review): DRF never calls has_object_permission
        # on create, so IsStakeResolutionBeatStoryOwnerOrStaff alone lets any
        # authenticated user POST a StakeResolution onto anyone's stake. Enforce
        # the same ownership walk here. On re-point, both the old and new
        # stake's beat's story must be owned. Ownership before lock (#1770
        # review): a non-owner probing a foreign stake must get the permission
        # error, never learn the lock state.
        if not is_staff:
            owners_ok = stake is not None and user_owns_beat_story(cast(Any, user), stake.beat)
            if is_repoint:
                owners_ok = owners_ok and user_owns_beat_story(cast(Any, user), old_stake.beat)
            if not owners_ok:
                msg = "You do not have permission to author a resolution on this stake."
                raise serializers.ValidationError(msg)

        # Lock check (#1770 PR1 review): re-pointing to/from a stake whose beat
        # is locked is rejected either way — check both sides when re-pointing.
        # Completed-beat check (#1770 PR3 review): the open-activation lock
        # alone leaves a hole — the completion tail closes the activation
        # while stakes can still pend for a GM pick, which would reopen
        # editing on a contract that already ran. Contract editing ends when
        # the beat completes (pillar 8's spirit).
        stakes_to_check = [stake] if not is_repoint else [stake, old_stake]
        for candidate in stakes_to_check:
            if candidate is not None and get_open_activation(candidate.beat) is not None:
                msg = "This beat's stakes contract is locked by an open activation."
                raise serializers.ValidationError(msg)
            if candidate is not None and candidate.beat.outcome != BeatOutcome.UNSATISFIED:
                msg = "This beat has completed; its stakes contract can no longer be edited."
                raise serializers.ValidationError(msg)

        self._validate_writer_payloads(attrs, stake)

        self._validate_writer_payloads(attrs, stake)

        return attrs

    def _validate_writer_payloads(self, attrs: Any, stake: Any) -> None:
        """Pillar-12 no-fiat guard on the writer payloads (#1770 PR2).

        Merges attrs with the instance (partial update) and rejects payload
        combinations that don't fit the stake's subject kind — most
        importantly, any lifecycle write outside a non-player-held NPC_FATE
        subject (removal is mechanically mediated, never branch fiat).
        """
        from world.stories.services.stake_resolution import (  # noqa: PLC0415
            stake_resolution_payload_problems,
        )

        def merged(field_name: str, default: Any) -> Any:
            if field_name in attrs:
                return attrs[field_name]
            if self.instance is not None:
                return getattr(self.instance, field_name)
            return default

        if stake is None:
            return
        problems = stake_resolution_payload_problems(
            stake=stake,
            forfeits_subject_item=merged("forfeits_subject_item", default=False),
            subject_standing_delta=merged("subject_standing_delta", default=0),
            sets_subject_lifecycle=merged("sets_subject_lifecycle", default=""),
            machine_match_lifecycle_state=merged("machine_match_lifecycle_state", default=""),
        )
        if problems:
            raise serializers.ValidationError({p.field: p.message for p in problems})


class StakeContractActivationSerializer(serializers.ModelSerializer):
    """Read-only full serializer for StakeContractActivation (#1770 pillars 7-8)."""

    class Meta:
        model = StakeContractActivation
        fields = [
            "id",
            "beat",
            "locked_at",
            "resolved_at",
            "party_average_level",
            "declared_target_level",
            "declared_risk",
            "effective_risk",
            "is_ready",
            "readiness_notes",
        ]
        read_only_fields = fields


class StakeSummarySerializer(serializers.ModelSerializer):
    """Player-visible summary of one Stake (#1770 pillar 9).

    What is wagered is visible; branch contents stay hidden — resolutions
    (consequence pools, escalations, narrative) are deliberately NOT fields
    here and must never be added.
    """

    severity_label = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = Stake
        fields = ["id", "player_summary", "severity", "severity_label"]
        read_only_fields = fields


class StakesSummarySerializer(serializers.Serializer):
    """Beat-level stakes summary shown at every opt-in surface (#1770 pillar 9).

    Read-only wire shape; build the payload via ``stakes_summary_for_beat``.
    ``effective_risk`` is the open activation's locked value when one exists,
    else the declared risk.
    """

    declared_risk = serializers.CharField(read_only=True)
    effective_risk = serializers.CharField(read_only=True)
    is_ready = serializers.BooleanField(read_only=True)
    stakes = StakeSummarySerializer(many=True, read_only=True)


def stakes_summary_for_beat(beat: Beat) -> dict:
    """Build the player-visible stakes-summary payload for a beat.

    Shared by the BeatViewSet ``stakes-summary`` endpoint and the combat
    consent-prompt surface (``combat_stakes``) so the shape stays single-
    sourced. Leaks only player_summary/severity by design (#1770 pillar 9).
    """
    from world.stories.services.stakes import (  # noqa: PLC0415
        effective_risk_for_beat,
        validate_stakes_readiness,
    )

    return StakesSummarySerializer(
        {
            "declared_risk": beat.risk,
            "effective_risk": effective_risk_for_beat(beat),
            "is_ready": validate_stakes_readiness(beat).is_ready,
            "stakes": beat.stakes.all(),
        }
    ).data
