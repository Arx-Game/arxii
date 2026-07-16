from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from evennia.objects.models import ObjectDB
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from world.character_sheets.models import CharacterSheet
from world.events.models import Event
from world.gm.constants import GMTableStatus
from world.gm.models import GMLevelCap, GMProfile, GMTable
from world.gm.serializers import GMProfileSerializer
from world.items.models import ItemInstance
from world.missions.models import MissionTemplate
from world.scenes.models import Persona
from world.societies.constants import RenownRisk
from world.societies.models import Organization, Society
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    CrossoverInviteStatus,
    CustodyClearanceStatus,
    CustodyScope,
    ProgressStatus,
    SessionRequestStatus,
    StakeResolutionColumn,
    StakeRewardSink,
    StakeSubjectKind,
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
    CanonReview,
    Chapter,
    CrossoverInvite,
    CustodyClearance,
    Episode,
    EpisodeProgressionRequirement,
    EpisodeResolution,
    EpisodeScene,
    Era,
    GlobalStoryProgress,
    GroupStoryProgress,
    GroupStoryRequest,
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
    StoryProtectedSubject,
    StoryTrustRequirement,
    TableBulletinPost,
    TableBulletinReply,
    Transition,
    TransitionRequiredOutcome,
    TreasuredSignoff,
    TrustCategory,
    TrustCategoryFeedbackRating,
)
from world.stories.permissions import user_owns_or_leads_story
from world.stories.types import (
    AnyStoryProgress,
    ConnectionType,
    StoryLogBeatEntry,
    StoryLogEpisodeEntry,
)

_STAKES_LOCKED_MESSAGE = "This beat's stakes contract is locked by an open activation."


def _custody_blocked_message(verdict: Any) -> str:
    """Disclosure-safe custody-block message (#2001 Task 4).

    Shared by StakeSerializer and StakeResolutionSerializer's custody gates.
    Never the protecting story's title or notes (ADR-0033-style disclosure
    posture) — only the custodian GM's username, or a staff-routed fallback
    when the protecting story is orphaned (no primary_table/GM to name).
    """
    if verdict.custodian_gm_username:
        return (
            "This subject is under another story's custody — request clearance "
            f"from GM {verdict.custodian_gm_username}."
        )
    return (
        "This subject is under another story's custody — request clearance "
        "from the story's GM via staff."
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
        # Suppression justified: queryset annotation probe; absent outside the annotating viewset.
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
            "impact_tier",
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
    tenure_id = serializers.SerializerMethodField()
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
            "impact_tier",
            "owners",
            "active_gms",
            "trust_requirements",
            "character_sheet",
            "tenure_id",
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
            "tenure_id",
            "primary_table",
            "chapters_count",
            "created_at",
            "updated_at",
            "completed_at",
        ]

    def get_trust_requirements(self, obj):
        """Get trust requirements for this story"""
        return obj.get_trust_requirements_summary()

    def get_tenure_id(self, obj: Story) -> int | None:
        """The current tenure of this CHARACTER-scope story's character (whoever is
        currently playing them) — coincides with the viewer's own tenure only for
        that player; other viewers get an inert value since
        `TreasuredSignoffPrompt`'s own player-scoped queries return nothing for a
        `tenure_id` that isn't theirs.

        Null for GROUP/GLOBAL-scope stories (no character_sheet) and for a
        CHARACTER-scope story whose character has no current tenure.
        """
        sheet = obj.character_sheet
        if sheet is None:
            return None
        # OneToOne reverse accessor may not exist.
        entry = sheet.roster_entry_or_none
        tenure = entry.current_tenure if entry else None
        return tenure.pk if tenure else None

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
    episode_id = serializers.IntegerField(read_only=True)
    scene_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = EpisodeScene
        fields = [
            "id",
            "episode",
            "scene",
            "episode_id",
            "scene_id",
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
        """Create feedback with category ratings, crediting the reviewed GM (#2123)."""
        from world.stories.services.feedback import submit_story_feedback  # noqa: PLC0415

        category_ratings_data = validated_data.pop("category_ratings", [])
        return submit_story_feedback(
            story=validated_data["story"],
            reviewer=validated_data["reviewer"],
            reviewed_player=validated_data["reviewed_player"],
            is_gm_feedback=validated_data.get("is_gm_feedback", False),
            comments=validated_data["comments"],
            category_ratings=category_ratings_data,
        )

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


def _gm_max_risk(user) -> str:
    """RenownRisk ceiling for a non-staff author: their GMLevelCap.max_beat_risk.

    No GMProfile or no cap row → RenownRisk.NONE.
    """
    try:
        gm_profile = user.gm_profile
    except GMProfile.DoesNotExist:
        return RenownRisk.NONE
    try:
        cap = GMLevelCap.objects.get(level=gm_profile.level)
    except GMLevelCap.DoesNotExist:
        return RenownRisk.NONE
    return cap.max_beat_risk


def _gm_allows_custom_stakes(user) -> bool:
    """Whether a non-staff author's GMLevelCap permits custom (template=null) stakes.

    No GMProfile or no cap row → False.
    """
    try:
        cap = GMLevelCap.objects.get(level=user.gm_profile.level)
    except (GMProfile.DoesNotExist, GMLevelCap.DoesNotExist):
        return False
    return cap.allow_custom_stakes


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
            "required_mission",
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

    def to_representation(self, instance: Beat) -> dict[str, Any]:
        """Gate ``internal_description`` for non-privileged viewers (#1923).

        ``internal_description`` is GM-only authoring text (the real predicate
        + meaning). It must not surface to players — mirroring the story-log
        contract (``visible_internal_description`` is ``None`` unless the
        viewer's role is staff/lead_gm) and the ``_gm_text_gate`` pattern.
        Privilege is decided by the shared ``can_view_story_gm_text``
        predicate (staff / Lead GM / story owner). When there is no request in
        context we default to the most-restrictive treatment so the field
        never leaks by default.
        """
        from world.stories.permissions import can_view_story_gm_text  # noqa: PLC0415

        data = super().to_representation(instance)
        request = self.context.get("request")
        user = request.user if request is not None else None
        story = instance.episode.chapter.story
        if user is None or not can_view_story_gm_text(user, story):
            data["internal_description"] = None
        return data

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
                "required_mission",
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

        self._check_beat_ownership(user, is_staff, merged)

        if merged_risk != RenownRisk.NONE and not is_staff:
            from world.stories.services.stakes import risk_index  # noqa: PLC0415

            if risk_index(merged_risk) > risk_index(_gm_max_risk(user)):
                raise serializers.ValidationError(
                    {
                        "risk": (
                            "Your GM level does not permit authoring beats at this risk "
                            "tier. Higher tiers unlock as staff promote your GM level."
                        )
                    }
                )
        return attrs

    def _check_beat_ownership(self, user: Any, is_staff: bool, merged: dict[str, Any]) -> None:
        """Reject the write unless staff or the requesting user owns the episode's story.

        #1770 PR1 review, fold-in: DRF never calls has_object_permission on
        create, so IsBeatStoryOwnerOrStaff alone lets any authenticated user
        POST a Beat onto anyone's episode. Enforce the same ownership walk here
        via the shared predicate. On re-point (the episode FK is being changed),
        both the old and new episode's story must be owned by the requesting user.
        """
        from world.stories.permissions import user_owns_episode_story  # noqa: PLC0415

        if is_staff:
            return
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
            self._validate_stake_row(stake, required_stake_column, required_outcome, beat)
        else:
            self._validate_outcome_row(required_outcome, required_stake_column)

        return attrs

    def _validate_stake_row(
        self, stake: Any, required_stake_column: str, required_outcome: str, beat: Any
    ) -> None:
        """Validate a stake-level predicate row (stake set, outcome blank)."""
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

    def _validate_outcome_row(self, required_outcome: str, required_stake_column: str) -> None:
        """Validate a beat-level predicate row (outcome set, stake null)."""
        if not required_outcome:
            raise serializers.ValidationError(
                {"required_outcome": "Required when stake is not set."}
            )
        if required_stake_column:
            raise serializers.ValidationError(
                {"required_stake_column": "Only allowed when stake is set."}
            )


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


class GroupStoryRequestSerializer(serializers.ModelSerializer):
    """Read serializer for GroupStoryRequest — the covenant-GM recruitment queue (#2119)."""

    class Meta:
        model = GroupStoryRequest
        fields = [
            "id",
            "covenant",
            "requested_by_account",
            "message",
            "status",
            "claimed_by",
            "created_story",
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
# #2002: Crossover invite serializers
# ---------------------------------------------------------------------------


class CrossoverInviteSerializer(serializers.ModelSerializer):
    """Read serializer for CrossoverInvite records (#2002)."""

    from_gm_account = serializers.IntegerField(read_only=True)

    class Meta:
        model = CrossoverInvite
        fields = [
            "id",
            "event",
            "from_gm",
            "from_gm_account",
            "to_story",
            "proposed_episode",
            "accepted_episode",
            "message",
            "response_note",
            "status",
            "created_at",
            "responded_at",
            "updated_at",
        ]
        read_only_fields = fields


class CrossoverInviteCreateSerializer(serializers.Serializer):
    """Input for POST /api/crossover-invites/.

    Context required:
        request: DRF request (for user identity + GMProfile resolution).

    Validates:
        - to_story exists (PrimaryKeyRelatedField).
        - event exists (PrimaryKeyRelatedField).
        - proposed_episode (if given) belongs to to_story.

    Stores ``from_gm`` (GMProfile) in validated_data.
    """

    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())
    to_story = serializers.PrimaryKeyRelatedField(queryset=Story.objects.all())
    proposed_episode = serializers.PrimaryKeyRelatedField(
        queryset=Episode.objects.all(), required=False
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        ep = attrs.get("proposed_episode")
        if ep is not None and ep.chapter.story_id != attrs["to_story"].pk:
            msg = "proposed_episode does not belong to to_story."
            raise serializers.ValidationError({"proposed_episode": msg})
        return attrs


class CrossoverInviteAcceptSerializer(serializers.Serializer):
    """Input for POST /api/crossover-invites/{id}/accept/.

    Context required:
        invite (CrossoverInvite): the invite being accepted.

    Validates:
        - invite.status == PENDING
    """

    accepted_episode = serializers.PrimaryKeyRelatedField(
        queryset=Episode.objects.all(), required=False
    )
    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        invite: CrossoverInvite = self.context["invite"]
        if invite.status != CrossoverInviteStatus.PENDING:
            msg = "Only PENDING crossover invites can be accepted."
            raise serializers.ValidationError({"non_field_errors": msg})
        return attrs


class CrossoverInviteDeclineSerializer(serializers.Serializer):
    """Input for POST /api/crossover-invites/{id}/decline/.

    Context required:
        invite (CrossoverInvite): the invite being declined.

    Validates:
        - invite.status == PENDING
    """

    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        invite: CrossoverInvite = self.context["invite"]
        if invite.status != CrossoverInviteStatus.PENDING:
            msg = "Only PENDING crossover invites can be declined."
            raise serializers.ValidationError({"non_field_errors": msg})
        return attrs


class CrossoverInviteWithdrawSerializer(serializers.Serializer):
    """Input for POST /api/crossover-invites/{id}/withdraw/.

    Context required:
        invite (CrossoverInvite): the invite being withdrawn.

    Validates:
        - invite.status == PENDING
    """

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        invite: CrossoverInvite = self.context["invite"]
        if invite.status != CrossoverInviteStatus.PENDING:
            msg = "Only PENDING crossover invites can be withdrawn."
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
        # Suppression justified: queryset annotation probe; absent outside the annotating viewset.
        reply_list = getattr(obj, "replies_cached", None)  # noqa: GETATTR_LITERAL
        if reply_list is None:
            reply_list = list(obj.replies.select_related("author_persona").all())
        return TableBulletinReplySerializer(reply_list, many=True).data


def resolve_own_bulletin_persona(request: Any, supplied: Persona | None) -> Persona:
    """Return the persona to author a bulletin as, enforcing account ownership.

    A GM table is account-scoped, not character-scoped (2026-07 audit): the web
    surface has no in-game persona to pass, so ``supplied`` is normally ``None``
    and we resolve one of the requester's own personas server-side (the active
    face of their first character). When a persona IS supplied it must belong to
    the requesting account — the ownership check the serializer docstrings always
    claimed but never enforced (a foreign persona would previously have posted
    successfully).
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if request is None:
        msg = "Request context is required."
        raise serializers.ValidationError(msg)

    if supplied is not None:
        # Staff act administratively and may author as any persona (they already
        # bypass the table-ownership check); a non-staff caller's supplied
        # persona must belong to their own account.
        if not request.user.is_staff:
            owned_ids = set(get_account_personas(request))
            if supplied.pk not in owned_ids:
                msg = "That persona does not belong to your account."
                raise serializers.ValidationError({"author_persona": msg})
        return supplied

    entry = RosterEntry.objects.for_account(request.user).first()
    sheet = entry.character_sheet if entry is not None else None
    if sheet is None:
        msg = "You have no character to author a bulletin as."
        raise serializers.ValidationError({"author_persona": msg})
    return active_persona_for_sheet(sheet)


class CreateBulletinPostInputSerializer(serializers.Serializer):
    """Input for POST /api/table-bulletin-posts/.

    Validates:
    - ``table`` exists and user is its Lead GM (or staff)
    - ``story`` (if set) belongs to ``table`` (story.primary_table == table)
    - ``author_persona`` belongs to the requesting user's account

    ``author_persona`` is optional (2026-07 audit): a GM table is account-scoped,
    not tied to a specific character, so the frontend has no in-game persona to
    pass — omit it and the requester's own persona is resolved server-side.
    When supplied, it MUST belong to the requesting account (the ownership check
    the docstring always claimed but never enforced).

    Stores validated model instances in validated_data.
    """

    table = serializers.PrimaryKeyRelatedField(queryset=GMTable.objects.all())
    story = serializers.PrimaryKeyRelatedField(
        queryset=Story.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    author_persona = serializers.PrimaryKeyRelatedField(
        queryset=Persona.objects.all(),
        required=False,
        default=None,
    )
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    allow_replies = serializers.BooleanField(required=False, default=True)

    def validate_table(self, table: GMTable) -> GMTable:
        """User must be the Lead GM of the table (or staff)."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context is required."
            raise serializers.ValidationError(msg)
        if request.user.is_staff:
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
        """Validate story↔table and resolve/authorize the author persona."""
        table: GMTable = attrs["table"]
        story: Story | None = attrs.get("story")
        if story is not None and story.primary_table_id != table.pk:
            msg = "The selected story is not assigned to this table."
            raise serializers.ValidationError({"story": msg})
        attrs["author_persona"] = resolve_own_bulletin_persona(
            self.context.get("request"), attrs.get("author_persona")
        )
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
    author_persona = serializers.PrimaryKeyRelatedField(
        queryset=Persona.objects.all(),
        required=False,
        default=None,
    )
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

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        """Resolve/authorize the author persona (optional → own persona, #audit2)."""
        attrs["author_persona"] = resolve_own_bulletin_persona(
            self.context.get("request"), attrs.get("author_persona")
        )
        return attrs


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
            msg = _STAKES_LOCKED_MESSAGE
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


class ResolveForeclosureInputSerializer(serializers.Serializer):
    """Input for POST /api/stories/{id}/resolve-foreclosure/.

    Context required:
        story (Story): the story whose foreclosed thread is being wrapped up.

    Validates (Layer 2): scope matches the story, the target discriminator is
    correct for the scope, and the resolved progress record is FORECLOSED and
    not already resolved. Surfaces violations as 400. ``resolved_by`` is
    stamped from the requesting user's GMProfile in the view — never accepted
    from client input.
    """

    scope = serializers.ChoiceField(choices=StoryScope.choices)
    character_sheet = serializers.PrimaryKeyRelatedField(
        queryset=CharacterSheet.objects.all(), required=False, allow_null=True
    )
    gm_table = serializers.PrimaryKeyRelatedField(
        queryset=GMTable.objects.all(), required=False, allow_null=True
    )

    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        story: Story = self.context["story"]
        scope = attrs["scope"]
        if scope != story.scope:
            msg = f"Scope {scope!r} does not match this story's scope {story.scope!r}."
            raise serializers.ValidationError({"scope": msg})
        progress = self._resolve_progress(story, scope, attrs)
        if progress is None:
            msg = "No progress record found for this story and scope."
            raise serializers.ValidationError({"non_field_errors": msg})
        if progress.status != ProgressStatus.FORECLOSED:
            msg = "This thread is not foreclosed."
            raise serializers.ValidationError({"non_field_errors": msg})
        attrs["progress"] = progress
        return attrs

    def _resolve_progress(self, story: Story, scope: str, attrs: Any) -> AnyStoryProgress | None:
        if scope == StoryScope.CHARACTER:
            if attrs.get("character_sheet") is None:
                msg = "character_sheet is required for CHARACTER scope."
                raise serializers.ValidationError({"character_sheet": msg})
            return story.progress_records.filter(character_sheet=attrs["character_sheet"]).first()
        if scope == StoryScope.GROUP:
            if attrs.get("gm_table") is None:
                msg = "gm_table is required for GROUP scope."
                raise serializers.ValidationError({"gm_table": msg})
            return story.group_progress_records.filter(gm_table=attrs["gm_table"]).first()
        return story.global_progress if hasattr(story, "global_progress") else None


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
    band (by risk_index). The template-null (CUSTOM) path is gated to staff or
    a non-staff GM whose GMLevelCap.allow_custom_stakes is set (see
    `_gm_allows_custom_stakes`), mirroring BeatSerializer.validate's risk gate
    in style. Any write (create or update) is rejected while the beat carries
    an open StakeContractActivation — the lock (#1770 pillar 8).
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
            self._apply_template_defaults(template, beat, attrs)
        else:
            self._validate_custom_stake(is_staff, user, merged)

        self._check_boundaries(beat, attrs)

        self._check_custody(beat, attrs, user)

        return attrs

    def _apply_template_defaults(self, template: Any, beat: Any, attrs: Any) -> None:
        """Band the template against the beat's risk and default subject fields."""
        from world.stories.services.stakes import risk_index  # noqa: PLC0415

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

    def _validate_custom_stake(self, is_staff: bool, user: Any, merged: dict[str, Any]) -> None:
        """Gate custom stakes (template=null) to staff or a permitting GMLevelCap (#2000)."""
        if not is_staff and not _gm_allows_custom_stakes(user):
            raise serializers.ValidationError(
                {
                    "template": (
                        "Only staff or Senior GMs may author custom stakes "
                        "(template=null). Use a StakeTemplate instead."
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

    def _candidate_subject_identity(self, attrs: Any) -> Any:
        """This write's effective wagered-subject identity (#2001 Task 4).

        Merges attrs with the instance exactly like ``_candidate_stake``
        (partial update falls back to the current row's values), but returns
        the typed-FK-or-label identity tuple directly — ``check_subject_custody``
        only needs the identity, not a full (unsaved, un-pk'd) ``Stake`` row.
        """
        from world.stories.services.boundaries import _subject_identity  # noqa: PLC0415

        def merged(field_name: str, default: Any = None) -> Any:
            if field_name in attrs:
                return attrs[field_name]
            if self.instance is not None:
                return getattr(self.instance, field_name)
            return default

        subject_sheet = merged("subject_sheet")
        subject_item = merged("subject_item")
        subject_society = merged("subject_society")
        subject_organization = merged("subject_organization")
        return _subject_identity(
            merged("subject_kind", default=""),
            subject_sheet.pk if subject_sheet is not None else None,
            subject_item.pk if subject_item is not None else None,
            subject_society.pk if subject_society is not None else None,
            subject_organization.pk if subject_organization is not None else None,
            merged("subject_label", default=""),
        )

    def _check_custody(self, beat: Any, attrs: Any, user: Any) -> None:
        """Authoring-time custody gate (#2001 Task 4).

        Resolutions don't exist yet at authoring time, so this always checks
        at APPEAR scope (the weakest guarantee — merely wagering the subject
        into a contract). A writer payload later raising the reach to
        HARM/REMOVE is re-checked at that scope by
        ``StakeResolutionSerializer.validate``. Staff bypass and the
        acting-story/participant/clearance rules all live inside
        ``check_subject_custody`` itself — this is a single call, not a
        duplicate gate. Never leak the protecting story's identity in the
        error (``_custody_blocked_message``, ADR-0033-style disclosure).
        """
        if beat is None:
            return
        from world.stories.services.custody import check_subject_custody  # noqa: PLC0415

        verdict = check_subject_custody(
            subject_identity=self._candidate_subject_identity(attrs),
            actor_account=user,
            scope=CustodyScope.APPEAR,
            acting_story=beat.episode.chapter.story,
        )
        if not verdict.allowed:
            raise serializers.ValidationError(_custody_blocked_message(verdict))


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

        self._check_reward_line_ownership(user, is_staff, resolution, old_resolution, is_repoint)

        self._check_resolution_lock(resolution, old_resolution, is_repoint)

        # WIN-column only (#1770 PR3 review): a "consolation" line on a
        # LOSS/WITHDRAWAL branch would be silently inert — refuse it.
        if resolution is not None and resolution.column != StakeResolutionColumn.WIN:
            raise serializers.ValidationError(
                {"resolution": "Reward lines only attach to WIN-column resolutions."}
            )

        self._validate_sink_shape(attrs)

        return attrs

    def _check_reward_line_ownership(
        self, user: Any, is_staff: bool, resolution: Any, old_resolution: Any, is_repoint: bool
    ) -> None:
        """Reject the write unless staff or the requesting user owns the resolution's beat story.

        #1770 PR3 review: DRF never calls has_object_permission on create, so
        IsStakeRewardLineBeatStoryOwnerOrStaff alone would let any authenticated
        user POST a reward line onto anyone's resolution. Ownership before lock
        — a non-owner probing a foreign resolution must get the permission
        error, never learn the lock state.
        """
        from world.stories.permissions import user_owns_beat_story  # noqa: PLC0415

        if is_staff:
            return
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

    def _check_resolution_lock(
        self, resolution: Any, old_resolution: Any, is_repoint: bool
    ) -> None:
        """Reject the write if any involved resolution's beat is locked or completed.

        #1770 PR3 review: re-pointing to/from a resolution whose beat is locked
        is rejected either way. Once the completion tail closes the activation
        (with stakes possibly pending a GM pick), the open-activation lock no
        longer bites — without the completed-beat check reward lines could be
        re-authored after the contract ran and pay out on the stale activation's
        readiness verdict.
        """
        from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

        resolutions_to_check = [resolution] if not is_repoint else [resolution, old_resolution]
        for candidate in resolutions_to_check:
            if candidate is None:
                continue
            if get_open_activation(candidate.stake.beat) is not None:
                msg = _STAKES_LOCKED_MESSAGE
                raise serializers.ValidationError(msg)
            if candidate.stake.beat.outcome != BeatOutcome.UNSATISFIED:
                msg = "This beat has completed; its stakes contract can no longer be edited."
                raise serializers.ValidationError(msg)

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
        old_stake = self.instance.stake if self.instance is not None else None
        stake = attrs.get("stake") or old_stake
        is_repoint = old_stake is not None and stake is not None and old_stake.pk != stake.pk

        request = self.context.get("request")
        user = request.user if request is not None else None
        # user.is_staff is safe on AccountDB and AnonymousUser; bool() guards None.
        is_staff = bool(user is not None and user.is_staff)

        self._enforce_ownership_gate(stake, old_stake, is_repoint, user, is_staff)
        self._enforce_lock_state(stake, old_stake, is_repoint)

        self._validate_writer_payloads(attrs, stake)

        self._check_writer_custody(attrs, stake, user)

        return attrs

    def _enforce_ownership_gate(
        self, stake: Any, old_stake: Any, is_repoint: bool, user: Any, is_staff: bool
    ) -> None:
        """Ownership gate (#1770 PR1 review).

        DRF never calls has_object_permission on create, so
        IsStakeResolutionBeatStoryOwnerOrStaff alone lets any authenticated user
        POST a StakeResolution onto anyone's stake. Enforce the same ownership
        walk here. On re-point, both the old and new stake's beat's story must be
        owned. Ownership before lock (#1770 review): a non-owner probing a
        foreign stake must get the permission error, never learn the lock state.
        """
        from world.stories.permissions import user_owns_beat_story  # noqa: PLC0415

        if is_staff:
            return
        owners_ok = stake is not None and user_owns_beat_story(cast(Any, user), stake.beat)
        if is_repoint:
            owners_ok = owners_ok and user_owns_beat_story(cast(Any, user), old_stake.beat)
        if not owners_ok:
            msg = "You do not have permission to author a resolution on this stake."
            raise serializers.ValidationError(msg)

    def _enforce_lock_state(self, stake: Any, old_stake: Any, is_repoint: bool) -> None:
        """Lock check (#1770 PR1 review) + completed-beat check (#1770 PR3 review).

        Re-pointing to/from a stake whose beat is locked is rejected either way —
        check both sides when re-pointing. The open-activation lock alone leaves a
        hole — the completion tail closes the activation while stakes can still
        pend for a GM pick, which would reopen editing on a contract that already
        ran. Contract editing ends when the beat completes (pillar 8's spirit).
        """
        from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

        stakes_to_check = [stake] if not is_repoint else [stake, old_stake]
        for candidate in stakes_to_check:
            if candidate is not None and get_open_activation(candidate.beat) is not None:
                msg = _STAKES_LOCKED_MESSAGE
                raise serializers.ValidationError(msg)
            if candidate is not None and candidate.beat.outcome != BeatOutcome.UNSATISFIED:
                msg = "This beat has completed; its stakes contract can no longer be edited."
                raise serializers.ValidationError(msg)

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

    def _writer_payload_scope(self, attrs: Any) -> str:
        """The custody scope THIS write's writer-payload combination reaches for.

        Mirrors ``custody._stake_intended_scope``'s ladder, but over just this
        write's merged payload rather than the stake's full authored
        resolution set — a re-check scoped to the one branch actually being
        authored/edited (#2001 Task 4).
        """

        def merged(field_name: str, default: Any) -> Any:
            if field_name in attrs:
                return attrs[field_name]
            if self.instance is not None:
                return getattr(self.instance, field_name)
            return default

        sets_subject_lifecycle = merged("sets_subject_lifecycle", default="")
        forfeits_subject_item = merged("forfeits_subject_item", default=False)
        subject_standing_delta = merged("subject_standing_delta", default=0)
        column = merged("column", default="")
        consequence_pool = merged("consequence_pool", default=None)

        if sets_subject_lifecycle or forfeits_subject_item:
            return CustodyScope.REMOVE
        if subject_standing_delta != 0 or (
            column == StakeResolutionColumn.LOSS and consequence_pool is not None
        ):
            return CustodyScope.HARM
        return CustodyScope.APPEAR

    def _check_writer_custody(self, attrs: Any, stake: Any, user: Any) -> None:
        """Re-check custody when this write raises the stake's reach (#2001 Task 4).

        A writer payload merely reaching APPEAR was already covered at
        stake-authoring time (``StakeSerializer._check_custody``) — this only
        re-checks when the payload raises the reach to HARM/REMOVE. Never
        leak the protecting story's identity in the error
        (``_custody_blocked_message``, ADR-0033-style disclosure).
        """
        if stake is None:
            return
        scope = self._writer_payload_scope(attrs)
        if scope == CustodyScope.APPEAR:
            return
        from world.stories.services.custody import custody_verdict_for_stake  # noqa: PLC0415

        verdict = custody_verdict_for_stake(stake, user, intended_scope=scope)
        if not verdict.allowed:
            raise serializers.ValidationError(_custody_blocked_message(verdict))


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


# ---------------------------------------------------------------------------
# #1771 task 6: sign-off grant/withdraw + GM stake-availability
#
# These live here (rather than world.boundaries.serializers) because they
# operate on stories-owned models (Beat, TreasuredSignoff) and call
# world.stories.services.boundaries — putting them in world.boundaries would
# make that app import world.stories, which ADR-0010's FK direction
# (specific->general) forbids. Task 5 made the identical call for the
# underlying service functions themselves.
# ---------------------------------------------------------------------------


class TreasuredSignoffSerializer(serializers.ModelSerializer):
    """A player's pre-scene sign-off to stake one of their treasured subjects.

    ``player_data`` is never client-writable — the viewset sets it from the
    requesting player, so a player can only sign off as themselves.
    ``treasured_subject`` must belong to one of the requesting player's own
    tenures (validated below) — a player cannot sign off on someone else's
    treasured subject.
    """

    active = serializers.BooleanField(read_only=True)

    class Meta:
        model = TreasuredSignoff
        fields = (
            "id",
            "beat",
            "player_data",
            "treasured_subject",
            "granted_at",
            "withdrawn_at",
            "active",
        )
        read_only_fields = ("id", "player_data", "granted_at", "withdrawn_at", "active")

    def validate_treasured_subject(self, treasured_subject: Any) -> Any:
        """Ensure the treasured subject belongs to the requesting player's own tenure."""
        request = self.context.get("request")
        if request is not None and hasattr(request.user, "player_data"):
            player_data = request.user.player_data
            if treasured_subject.owner.player_data_id != player_data.pk:
                msg = "You may only sign off on your own treasured subjects."
                raise serializers.ValidationError(msg)
        return treasured_subject


class StakeAvailabilitySerializer(serializers.Serializer):
    """GM-facing counts-only wire shape for ``world.stories.types.StakeAvailability``.

    Deliberately exactly three integer fields — ``available``/``blocked``/
    ``needs_signoff`` — and NOTHING else. ``blocked_reason_private`` must
    NEVER be added here (ADR-0033): a GM sees "3 available, 1 blocked, 2 need
    sign-off", never which stake or why.
    """

    available = serializers.IntegerField(read_only=True)
    blocked = serializers.IntegerField(read_only=True)
    needs_signoff = serializers.IntegerField(read_only=True)


class PendingTreasuredSignoffsSerializer(serializers.Serializer):
    """Player-safe wire shape for one world.stories.types.PendingTreasuredSignoffs entry (#1853).

    Exposes only the requesting player's own beat_id + treasured_subject_ids —
    the view-level query already guarantees no other player's data can appear
    here (ADR-0033); this serializer adds no fields beyond that.
    """

    beat_id = serializers.IntegerField(read_only=True)
    treasured_subject_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)


# ---------------------------------------------------------------------------
# Custody protection + clearance lifecycle (#2001 Task 6)
# ---------------------------------------------------------------------------


class StoryProtectedSubjectSerializer(serializers.ModelSerializer):
    """Full serializer for StoryProtectedSubject (#2001 Task 6).

    Enforces the model's exactly-one-subject invariant here (DRF serializers
    never call ``Model.clean()``) and the story-ownership gate on create/update
    — ``IsProtectedSubjectStoryOwnerOrStaff.has_object_permission`` alone
    cannot cover create, since DRF never calls object-level permissions for a
    row that does not exist yet.
    """

    class Meta:
        model = StoryProtectedSubject
        fields = [
            "id",
            "story",
            "subject_kind",
            "subject_sheet",
            "subject_item",
            "subject_society",
            "subject_organization",
            "subject_label",
            "beat",
            "is_active",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs: Any) -> Any:
        """Story-ownership gate, beat/story consistency, exactly-one-subject."""
        story = attrs.get("story", self.instance.story if self.instance is not None else None)
        if story is None:
            raise serializers.ValidationError({"story": "story is required."})

        request = self.context.get("request")
        user = request.user if request is not None else None
        is_staff = bool(user is not None and user.is_staff)
        if not is_staff and not user_owns_or_leads_story(user, story):
            raise serializers.ValidationError({"story": "You do not own or lead this story."})

        beat = attrs.get("beat", self.instance.beat if self.instance is not None else None)
        if beat is not None and beat.episode.chapter.story_id != story.pk:
            raise serializers.ValidationError(
                {"beat": "This beat does not belong to the same story."}
            )

        self._validate_exactly_one_subject(attrs)
        return attrs

    def _validate_exactly_one_subject(self, attrs: Any) -> None:
        """Mirror StoryProtectedSubject.clean()'s exactly-one-subject rule."""

        def effective(name: str) -> Any:
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name) if self.instance is not None else None

        typed_fields = ("subject_sheet", "subject_item", "subject_society", "subject_organization")
        populated = [name for name in typed_fields if effective(name) is not None]
        if effective("subject_label"):
            populated.append("subject_label")
        if len(populated) != 1:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "Exactly one of subject_sheet/subject_item/subject_society/"
                        "subject_organization/subject_label must be set "
                        f"(found: {populated or 'none'})."
                    )
                }
            )


class CustodyClearanceSerializer(serializers.ModelSerializer):
    """Read/response serializer for CustodyClearance (#2001 Task 6).

    Every field is read-only here — writes go through
    ``CustodyClearanceRequestSerializer`` (create) and the per-action input
    serializers (grant/deny/escalate/resolve/revoke), all of which route
    through ``world.stories.services.custody_clearance``. No nested
    notification/message data is exposed here, so the recipient-scoped
    ``related_story`` disclosure rule that module documents does not apply
    to this serializer.
    """

    class Meta:
        model = CustodyClearance
        fields = [
            "id",
            "protected_subject",
            "requested_by",
            "requesting_story",
            "requesting_beat",
            "scope",
            "status",
            "granted_by",
            "staff_resolver",
            "message",
            "response_note",
            "revoked_at",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields


class CustodyClearanceRequestSerializer(serializers.Serializer):
    """Input serializer for ``CustodyClearanceViewSet.create`` -> ``request_clearance``.

    Accepts EITHER of two mutually-exclusive paths to name the protected
    subject (Task 6 review Fix 4; ADR-0099 records the identity path as the
    ratified design, not just a workaround):

    - **pk path** — ``protected_subject`` directly. Deliberately uses an
      UNSCOPED-by-story queryset — a clearance request is inherently
      cross-story (the point is asking *another* story's custodian for
      permission), so scoping it to the requester's own stories would both
      defeat the feature and create a differential-error oracle. Scoping to
      ``is_active=True`` only still avoids oracling "exists but not
      requestable" vs. "does not exist": DRF's built-in PrimaryKeyRelatedField
      error is identical prose either way ("object does not exist"), so an
      inactive protection and a nonexistent pk are indistinguishable to the
      caller — no extra generic-message logic needed to enforce that.
    - **identity path** — ``subject_kind`` + exactly one of
      ``subject_sheet``/``subject_item``/``subject_society``/
      ``subject_organization``/``subject_label``, mirroring
      ``StoryProtectedSubjectSerializer``'s exactly-one-subject rule. For a
      blocked outsider GM who only ever learns the custodian's username (never
      the ``protected_subject`` pk — see ``CustodyVerdict``), this is the only
      self-serviceable path: it derives the same ``_subject_identity`` tuple
      ``world.stories.services.custody`` matches ``Stake`` rows against
      (``world.stories.services.custody_clearance.matching_active_protected_subjects``)
      and resolves to every active ``StoryProtectedSubject`` row sharing that
      identity — a subject can be independently protected by more than one
      story. No match raises the identical ``does_not_exist``-shaped error the
      pk path raises for an inactive/missing pk — same no-oracle guarantee,
      just reached from the identity side.

    On success, ``validated_data["_protections_to_request"]`` holds the
    protection rows the view should call ``request_clearance`` on, and
    ``validated_data["_already_pending_clearances"]`` holds pre-existing
    live (PENDING/ESCALATED) clearances for rows the identity path matched but
    the requester already has a live request against — skipped rather than
    re-requested (the partial-unique constraint would otherwise raise) and
    reported back as-is. The single-pk path never populates the latter list;
    a duplicate there is still a hard validation error, matching prior
    behavior exactly.
    """

    protected_subject = serializers.PrimaryKeyRelatedField(
        queryset=StoryProtectedSubject.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    subject_kind = serializers.ChoiceField(
        choices=StakeSubjectKind.choices, required=False, allow_null=True
    )
    subject_sheet = serializers.PrimaryKeyRelatedField(
        queryset=CharacterSheet.objects.all(), required=False, allow_null=True
    )
    subject_item = serializers.PrimaryKeyRelatedField(
        queryset=ItemInstance.objects.all(), required=False, allow_null=True
    )
    subject_society = serializers.PrimaryKeyRelatedField(
        queryset=Society.objects.all(), required=False, allow_null=True
    )
    subject_organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )
    subject_label = serializers.CharField(required=False, allow_blank=True, default="")
    scope = serializers.ChoiceField(choices=CustodyScope.choices)
    requesting_story = serializers.PrimaryKeyRelatedField(
        queryset=Story.objects.all(), required=False, allow_null=True
    )
    requesting_beat = serializers.PrimaryKeyRelatedField(
        queryset=Beat.objects.all(), required=False, allow_null=True
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:
        """GMProfile gate, exactly-one-of-{pk path, identity path}, resolve to protections."""
        request = self.context["request"]
        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            raise serializers.ValidationError(
                {"non_field_errors": ("You must have a GM profile to request custody clearance.")}
            ) from None

        protected_subject = attrs.get("protected_subject")
        subject_kind = attrs.get("subject_kind")
        if (protected_subject is not None) == (subject_kind is not None):
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "Provide exactly one of protected_subject, or subject_kind plus a "
                        "subject identity (subject_sheet/subject_item/subject_society/"
                        "subject_organization/subject_label)."
                    )
                }
            )

        scope = attrs["scope"]
        if protected_subject is not None:
            protections = [protected_subject]
        else:
            self._validate_identity_group(attrs)
            protections = self._matching_protections(subject_kind, attrs)
            if not protections:
                raise serializers.ValidationError(
                    {
                        "protected_subject": [
                            ErrorDetail(
                                'Invalid pk "identity" - object does not exist.',
                                code="does_not_exist",
                            )
                        ]
                    }
                )

        already_pending_by_subject_id = {
            clearance.protected_subject_id: clearance
            for clearance in CustodyClearance.objects.filter(
                protected_subject_id__in=[protection.pk for protection in protections],
                requested_by=gm_profile,
                scope=scope,
                status__in=(CustodyClearanceStatus.PENDING, CustodyClearanceStatus.ESCALATED),
            )
        }

        if protected_subject is not None and protected_subject.pk in already_pending_by_subject_id:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "You already have a live clearance request for this subject at this scope."
                    )
                }
            )

        attrs["requested_by"] = gm_profile
        attrs["_protections_to_request"] = [
            protection
            for protection in protections
            if protection.pk not in already_pending_by_subject_id
        ]
        attrs["_already_pending_clearances"] = list(already_pending_by_subject_id.values())
        return attrs

    def _validate_identity_group(self, attrs: Any) -> None:
        """Mirror ``StoryProtectedSubjectSerializer``'s exactly-one-subject rule."""
        typed_fields = ("subject_sheet", "subject_item", "subject_society", "subject_organization")
        populated = [name for name in typed_fields if attrs.get(name) is not None]
        if attrs.get("subject_label"):
            populated.append("subject_label")
        if len(populated) != 1:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "Exactly one of subject_sheet/subject_item/subject_society/"
                        "subject_organization/subject_label must be set alongside "
                        f"subject_kind (found: {populated or 'none'})."
                    )
                }
            )

    def _matching_protections(self, subject_kind: str, attrs: Any) -> list[StoryProtectedSubject]:
        """Resolve the identity-path fields to the matching active protection rows."""
        from world.stories.services.boundaries import _subject_identity  # noqa: PLC0415
        from world.stories.services.custody_clearance import (  # noqa: PLC0415
            matching_active_protected_subjects,
        )

        subject_sheet = attrs.get("subject_sheet")
        subject_item = attrs.get("subject_item")
        subject_society = attrs.get("subject_society")
        subject_organization = attrs.get("subject_organization")
        identity = _subject_identity(
            subject_kind,
            subject_sheet.pk if subject_sheet is not None else None,
            subject_item.pk if subject_item is not None else None,
            subject_society.pk if subject_society is not None else None,
            subject_organization.pk if subject_organization is not None else None,
            attrs.get("subject_label", ""),
        )
        return matching_active_protected_subjects(identity)


class CustodyClearanceDecisionInputSerializer(serializers.Serializer):
    """Input for grant/deny — validates the clearance is PENDING before the service call."""

    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:
        clearance = self.context["clearance"]
        if clearance.status != CustodyClearanceStatus.PENDING:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        f"This clearance is not PENDING (status={clearance.status!r}); "
                        "only a PENDING request can be granted or denied directly."
                    )
                }
            )
        return attrs


class CustodyClearanceEscalateInputSerializer(serializers.Serializer):
    """Input for escalate — validates DENIED-or-stale-PENDING eligibility up front."""

    def validate(self, attrs: Any) -> Any:
        from world.stories.services.custody_clearance import (  # noqa: PLC0415
            clearance_is_stale,
        )

        clearance = self.context["clearance"]
        is_denied = clearance.status == CustodyClearanceStatus.DENIED
        is_stale_pending = (
            clearance.status == CustodyClearanceStatus.PENDING and clearance_is_stale(clearance)
        )
        if not (is_denied or is_stale_pending):
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        f"This clearance (status={clearance.status!r}) is not eligible "
                        "for escalation — it must be DENIED, or PENDING and stale."
                    )
                }
            )
        return attrs


class CustodyClearanceResolveInputSerializer(serializers.Serializer):
    """Input for staff resolve — {grant: bool, response_note} — ESCALATED-only."""

    grant = serializers.BooleanField()
    response_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: Any) -> Any:
        clearance = self.context["clearance"]
        if clearance.status != CustodyClearanceStatus.ESCALATED:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        f"This clearance is not ESCALATED (status={clearance.status!r}); "
                        "only an escalated request can be staff-resolved."
                    )
                }
            )
        return attrs


class CustodyClearanceRevokeInputSerializer(serializers.Serializer):
    """Input for revoke — validates an active GRANTED clearance up front."""

    def validate(self, attrs: Any) -> Any:
        clearance = self.context["clearance"]
        if clearance.status != CustodyClearanceStatus.GRANTED or clearance.revoked_at is not None:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        f"This clearance is not an active GRANTED clearance "
                        f"(status={clearance.status!r}, revoked_at={clearance.revoked_at!r}) "
                        "and cannot be revoked."
                    )
                }
            )
        return attrs


class CanonReviewSerializer(serializers.ModelSerializer):
    """Read/response serializer for CanonReview (#2003).

    Every field is read-only here — writes go through the per-action input
    serializers (clear/changes) and the ``world.stories.services.canon_review``
    service. ``reviewer`` is the staff account that decided the review.
    """

    story = serializers.PrimaryKeyRelatedField(read_only=True)
    reviewer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CanonReview
        fields = [
            "id",
            "story",
            "tier",
            "status",
            "reviewer",
            "notes",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields


class CanonReviewClearInputSerializer(serializers.Serializer):
    """Input for ``CanonReviewViewSet.clear`` -> ``clear_canon_review``."""

    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_notes(self, notes: str) -> str:
        return notes


class CanonReviewChangesInputSerializer(serializers.Serializer):
    """Input for ``CanonReviewViewSet.changes`` -> ``request_changes``.

    ``notes`` is required — the Lead GM must be told what to change.
    """

    notes = serializers.CharField(required=True, allow_blank=False)

    def validate_notes(self, notes: str) -> str:
        if not notes.strip():
            msg = "Notes may not be blank when requesting changes."
            raise serializers.ValidationError(msg)
        return notes


class AssignMissionInputSerializer(serializers.Serializer):
    """POST /api/beats/{id}/assign-mission/ body (#2048).

    Defaults ``template`` from the beat's ``required_mission`` when not
    explicitly provided. Validates that a template is resolvable.
    """

    character = serializers.PrimaryKeyRelatedField(
        queryset=ObjectDB.objects.all(),
        help_text="The character to assign the mission to.",
    )
    template = serializers.PrimaryKeyRelatedField(
        queryset=MissionTemplate.objects.all(),
        required=False,
        allow_null=True,
        help_text="Optional: override the beat's required_mission template.",
    )

    _ERR_NO_TEMPLATE = "No template specified and the beat has no required_mission."

    def validate(self, attrs: dict) -> dict:
        beat = self.context.get("beat")
        if beat is not None:
            template = attrs.get("template") or beat.required_mission
            if template is None:
                raise serializers.ValidationError({"template": self._ERR_NO_TEMPLATE})
            attrs["template"] = template
        return attrs
