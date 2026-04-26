from http import HTTPMethod
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db import models
from django.db.models import Count, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from world.stories.constants import AssistantClaimStatus, SessionRequestStatus, StoryScope
from world.stories.filters import (
    AggregateBeatContributionFilter,
    AssistantGMClaimFilter,
    BeatFilter,
    ChapterFilter,
    EpisodeFilter,
    EpisodeProgressionRequirementFilter,
    EpisodeSceneFilter,
    GlobalStoryProgressFilter,
    GroupStoryProgressFilter,
    PlayerTrustFilter,
    SessionRequestFilter,
    StoryFeedbackFilter,
    StoryFilter,
    StoryParticipationFilter,
    TransitionFilter,
    TransitionRequiredOutcomeFilter,
)
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    Chapter,
    Episode,
    EpisodeProgressionRequirement,
    EpisodeScene,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    SessionRequest,
    Story,
    StoryFeedback,
    StoryParticipation,
    StoryProgress,
    Transition,
    TransitionRequiredOutcome,
)
from world.stories.pagination import (
    LargeResultsSetPagination,
    SmallResultsSetPagination,
    StandardResultsSetPagination,
)
from world.stories.permissions import (
    VIEWER_ROLE_NO_ACCESS,
    CanMarkBeat,
    CanParticipateInStory,
    IsAccountOfCharacterSheet,
    IsBeatStoryOwnerOrStaff,
    IsChapterStoryOwnerOrStaff,
    IsClaimantOrLeadGMOrStaff,
    IsClaimOwnerOrStaff,
    IsContributorOrLeadGMOrStaff,
    IsEpisodeStoryOwnerOrStaff,
    IsGlobalProgressReadableOrStaff,
    IsGMProfile,
    IsGroupProgressMemberOrStaff,
    IsLeadGMOnClaimStoryOrStaff,
    IsLeadGMOnEpisodeStoryOrStaff,
    IsLeadGMOnStoryOrStaff,
    IsLeadGMOnTransitionStoryOrStaff,
    IsParticipationOwnerOrStoryOwnerOrStaff,
    IsPlayerTrustOwnerOrStaff,
    IsReviewerOrStoryOwnerOrStaff,
    IsSessionRequestGMOrStaff,
    IsSessionRequestParticipantOrStaff,
    IsStoryOwnerOrStaff,
    classify_story_log_viewer_role,
)
from world.stories.serializers import (
    AggregateBeatContributionSerializer,
    ApproveClaimInputSerializer,
    AssistantGMClaimSerializer,
    BeatCompletionSerializer,
    BeatSerializer,
    CancelClaimInputSerializer,
    CancelSessionRequestInputSerializer,
    ChapterCreateSerializer,
    ChapterDetailSerializer,
    ChapterListSerializer,
    CompleteClaimInputSerializer,
    ContributeBeatInputSerializer,
    CreateEventFromSessionRequestInputSerializer,
    EpisodeCreateSerializer,
    EpisodeDetailSerializer,
    EpisodeListSerializer,
    EpisodeProgressionRequirementSerializer,
    EpisodeResolutionSerializer,
    EpisodeSceneSerializer,
    GlobalStoryProgressSerializer,
    GroupStoryProgressSerializer,
    MarkBeatInputSerializer,
    PlayerTrustSerializer,
    RejectClaimInputSerializer,
    RequestClaimInputSerializer,
    ResolveEpisodeInputSerializer,
    ResolveSessionRequestInputSerializer,
    SessionRequestSerializer,
    StoryCreateSerializer,
    StoryDetailSerializer,
    StoryFeedbackCreateSerializer,
    StoryFeedbackSerializer,
    StoryListSerializer,
    StoryLogSerializer,
    StoryParticipationSerializer,
    TransitionRequiredOutcomeSerializer,
    TransitionSerializer,
)
from world.stories.services.dashboards import STALE_STORY_DAYS, compute_story_status
from world.stories.services.participation import create_story_participation
from world.stories.services.progress import get_active_progress_for_story
from world.stories.services.story_log import serialize_story_log
from world.stories.types import AnyStoryProgress


class StoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Story model.
    Provides CRUD operations with proper permissions and filtering.
    """

    queryset = Story.objects.all()
    permission_classes = [IsStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = StoryFilter
    pagination_class = StandardResultsSetPagination
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "title", "status"]
    ordering = ["-updated_at"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return StoryListSerializer
        if self.action == "create":
            return StoryCreateSerializer
        return StoryDetailSerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        """Set the creator as an owner when creating a story"""
        story = serializer.save()
        story.owners.add(self.request.user)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[CanParticipateInStory])
    def apply_to_participate(self, request: Request, pk: int | None = None) -> Response:
        """Apply to participate in a story"""
        story = self.get_object()
        character_id = request.data.get("character_id")
        participation_level = request.data.get("participation_level", "optional")

        if not character_id:
            return Response(
                {"error": "character_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already participating
        if StoryParticipation.objects.filter(
            story=story,
            character_id=character_id,
        ).exists():
            return Response(
                {"error": "Already participating in this story"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

        try:
            character = ObjectDB.objects.get(pk=character_id)
        except ObjectDB.DoesNotExist:
            return Response({"error": "Character not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            participation = create_story_participation(
                story=story,
                character=character,
                participation_level=participation_level,
            )
        except ProtagonismLockedError as exc:
            return Response({"error": exc.user_message}, status=status.HTTP_403_FORBIDDEN)

        serializer = StoryParticipationSerializer(participation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.GET])
    def participants(self, request: Request, pk: int | None = None) -> Response:
        """Get all participants for a story"""
        story = self.get_object()
        participants = story.participants.filter(is_active=True)
        serializer = StoryParticipationSerializer(participants, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET])
    def chapters(self, request: Request, pk: int | None = None) -> Response:
        """Get all chapters for a story"""
        story = self.get_object()
        chapters = story.chapters.all().order_by("order")
        serializer = ChapterListSerializer(chapters, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET], url_path="log")
    def log(self, request: Request, pk: int | None = None) -> Response:
        """GET /api/stories/{id}/log/ — visibility-filtered story log.

        Returns a chronological list of beat completions and episode resolutions
        for this story, filtered to what the viewer is permitted to see:

        - staff: sees all fields including internal_description and gm_notes
        - lead_gm (story.primary_table.gm == request.user.gm_profile): same as staff
        - player (participant / story character owner / active group member): sees
          player-facing text; SECRET beat hints suppressed; no internal fields
        - no_access: 403

        The viewer role is determined by classify_story_log_viewer_role.
        """
        story = self.get_object()
        progress = get_active_progress_for_story(story)
        viewer_role = classify_story_log_viewer_role(request.user, story, progress)
        if viewer_role == VIEWER_ROLE_NO_ACCESS:
            msg = "You do not have access to this story's log."
            raise PermissionDenied(msg)
        log_entries = serialize_story_log(story=story, progress=progress, viewer_role=viewer_role)
        serializer = StoryLogSerializer(log_entries)
        return Response(serializer.data)


class StoryParticipationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for StoryParticipation model.
    Manages character participation in stories.
    """

    queryset = StoryParticipation.objects.all()
    serializer_class = StoryParticipationSerializer
    permission_classes = [IsParticipationOwnerOrStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryParticipationFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["joined_at", "participation_level"]
    ordering = ["-joined_at"]


class ChapterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Chapter model.
    Manages story chapters with proper story ownership permissions.
    """

    queryset = Chapter.objects.all()
    permission_classes = [IsChapterStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ChapterFilter
    pagination_class = SmallResultsSetPagination
    search_fields = ["title", "description", "summary"]
    ordering_fields = ["created_at", "order", "title"]
    ordering = ["story", "order"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return ChapterListSerializer
        if self.action == "create":
            return ChapterCreateSerializer
        return ChapterDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def episodes(self, request: Request, pk: int | None = None) -> Response:
        """Get all episodes for a chapter"""
        chapter = self.get_object()
        episodes = chapter.episodes.all().order_by("order")
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)


class EpisodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Episode model.
    Manages story episodes with narrative connection tracking.
    """

    queryset = Episode.objects.all()
    permission_classes = [IsEpisodeStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = EpisodeFilter
    pagination_class = SmallResultsSetPagination
    search_fields = ["title", "description", "summary"]
    ordering_fields = ["created_at", "order", "title"]
    ordering = ["chapter", "order"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return EpisodeListSerializer
        if self.action == "create":
            return EpisodeCreateSerializer
        return EpisodeDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def scenes(self, request: Request, pk: int | None = None) -> Response:
        """Get all scenes for an episode"""
        episode = self.get_object()
        episode_scenes = episode.episode_scenes.all().order_by("order")
        serializer = EpisodeSceneSerializer(episode_scenes, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/episodes/{id}/resolve/ — resolve the current progress for an episode.

        Lead GM or staff posts {progress_id?, chosen_transition?, gm_notes?} to
        advance the story's progress record past the current episode. Returns 201 on success.

        Note: NoEligibleTransitionError and AmbiguousTransitionError can fire from
        resolve_episode() for cases the serializer cannot pre-validate without
        duplicating get_eligible_transitions() logic. These are caught here and
        surfaced as 400 responses. They are genuine runtime errors, not
        user-input-validation errors.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.exceptions import StoryError  # noqa: PLC0415
        from world.stories.services.episodes import resolve_episode  # noqa: PLC0415

        episode = self.get_object()
        ser = ResolveEpisodeInputSerializer(data=request.data, context={"episode": episode})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None

        try:
            resolution = resolve_episode(
                progress=data["progress"],
                chosen_transition=data.get("chosen_transition"),
                gm_notes=data["gm_notes"],
                resolved_by=gm_profile,
            )
        except StoryError as exc:
            # Race condition / service-layer runtime errors:
            # NoEligibleTransitionError — no transitions are eligible (episode frontier).
            # AmbiguousTransitionError — multiple eligible transitions, GM must pick one.
            # These cannot be pre-validated by the serializer without duplicating
            # get_eligible_transitions() logic.
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            EpisodeResolutionSerializer(resolution).data, status=status.HTTP_201_CREATED
        )


class EpisodeSceneViewSet(viewsets.ModelViewSet):
    """
    ViewSet for EpisodeScene model.
    Manages the connection between episodes and scenes.
    """

    queryset = EpisodeScene.objects.all()
    serializer_class = EpisodeSceneSerializer
    permission_classes = [IsEpisodeStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = EpisodeSceneFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order"]
    ordering = ["episode", "order"]


class PlayerTrustViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PlayerTrust model.
    Manages player trust levels for content and GM activities.
    """

    queryset = PlayerTrust.objects.all()
    serializer_class = PlayerTrustSerializer
    permission_classes = [IsPlayerTrustOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = PlayerTrustFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = [
        "gm_trust_level",
        "antagonism_trust",
        "mature_themes_trust",
        "created_at",
        "updated_at",
    ]
    ordering = ["-updated_at"]

    @action(detail=False, methods=[HTTPMethod.GET])
    def my_trust(self, request: Request) -> Response:
        """Get the current user's trust profile"""
        try:
            trust_profile = PlayerTrust.objects.get(
                account=request.user,
            )
            serializer = self.get_serializer(trust_profile)
            return Response(serializer.data)
        except PlayerTrust.DoesNotExist:
            return Response(
                {"error": "Trust profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class StoryFeedbackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for StoryFeedback model.
    Manages feedback on player and GM performance in stories.
    """

    queryset = StoryFeedback.objects.all().order_by(
        "-created_at",
    )
    permission_classes = [IsReviewerOrStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryFeedbackFilter
    pagination_class = LargeResultsSetPagination
    ordering_fields = ["created_at", "is_positive", "is_gm_feedback"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "create":
            return StoryFeedbackCreateSerializer
        return StoryFeedbackSerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        """Set the reviewer as the current user when creating feedback"""
        serializer.save(reviewer=self.request.user)

    @action(detail=False, methods=[HTTPMethod.GET])
    def my_feedback(self, request: Request) -> Response:
        """Get feedback received by the current user"""
        feedback = self.get_queryset().filter(reviewed_player=request.user)

        # Apply filters manually since we're using a custom queryset
        filterset = self.filterset_class(request.GET, queryset=feedback)
        if filterset.is_valid():
            feedback = filterset.qs

        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=[HTTPMethod.GET])
    def feedback_given(self, request: Request) -> Response:
        """Get feedback given by the current user"""
        feedback = self.get_queryset().filter(reviewer=request.user)

        # Apply filters manually since we're using a custom queryset
        filterset = self.filterset_class(request.GET, queryset=feedback)
        if filterset.is_valid():
            feedback = filterset.qs

        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Phase 2 ViewSets
# ---------------------------------------------------------------------------


class GroupStoryProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for GroupStoryProgress — per-GMTable progress pointer.

    Read access: active members of the GMTable.
    Write access: Lead GM (GMTable.gm) and staff.
    """

    queryset = GroupStoryProgress.objects.select_related(
        "story",
        "gm_table",
        "current_episode",
    )
    serializer_class = GroupStoryProgressSerializer
    permission_classes = [IsGroupProgressMemberOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = GroupStoryProgressFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["started_at", "last_advanced_at", "is_active"]
    ordering = ["-last_advanced_at"]

    def get_queryset(self) -> QuerySet[GroupStoryProgress]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        # Active members: Persona -> character_sheet -> character (ObjectDB) -> db_account.
        member_q = models.Q(
            gm_table__memberships__persona__character_sheet__character__db_account=self.request.user,
            gm_table__memberships__left_at__isnull=True,
        )
        # Lead GMs can also see records for their own tables.
        lead_gm_q = models.Q(gm_table__gm=gm_profile) if gm_profile is not None else models.Q()
        return qs.filter(member_q | lead_gm_q).distinct()


class GlobalStoryProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for GlobalStoryProgress — singleton metaplot progress pointer.

    Read access: any authenticated user (metaplot is public).
    Write access: staff only.
    """

    queryset = GlobalStoryProgress.objects.select_related("story", "current_episode")
    serializer_class = GlobalStoryProgressSerializer
    permission_classes = [IsGlobalProgressReadableOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = GlobalStoryProgressFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["started_at", "last_advanced_at", "is_active"]
    ordering = ["-last_advanced_at"]


class AggregateBeatContributionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for AggregateBeatContribution.

    Writes go through record_aggregate_contribution service (Wave 11 action endpoints).
    Read access: the contributing character's account, story Lead GM (owner), or staff.
    """

    queryset = AggregateBeatContribution.objects.select_related(
        "beat__episode__chapter__story",
        "character_sheet__character",
        "roster_entry",
        "era",
    )
    serializer_class = AggregateBeatContributionSerializer
    permission_classes = [IsContributorOrLeadGMOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = AggregateBeatContributionFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["recorded_at", "points"]
    ordering = ["-recorded_at"]

    def get_queryset(self) -> QuerySet[AggregateBeatContribution]:
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        # Limit to contributions for characters this user owns, or stories they own
        return qs.filter(
            models.Q(character_sheet__character__db_account=self.request.user)
            | models.Q(beat__episode__chapter__story__owners=self.request.user)
        ).distinct()


class AssistantGMClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AssistantGMClaim.

    Read: ReadOnlyModelViewSet (list + retrieve).
    State transitions: custom @action endpoints (Wave 11):
      POST /api/assistant-gm-claims/request/ — request_claim
      POST /api/assistant-gm-claims/{id}/approve/ — approve_claim
      POST /api/assistant-gm-claims/{id}/reject/  — reject_claim
      POST /api/assistant-gm-claims/{id}/cancel/  — cancel_claim
      POST /api/assistant-gm-claims/{id}/complete/ — complete_claim

    Read access: the claiming AGM (assistant_gm.account), Lead GM (story owner), or staff.
    """

    queryset = AssistantGMClaim.objects.select_related(
        "beat__episode__chapter__story",
        "assistant_gm__account",
        "approved_by__account",
    )
    serializer_class = AssistantGMClaimSerializer
    permission_classes = [IsClaimantOrLeadGMOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = AssistantGMClaimFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["requested_at", "updated_at", "status"]
    ordering = ["-requested_at"]

    def get_queryset(self) -> QuerySet[AssistantGMClaim]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        filters_q = models.Q(beat__episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assistant_gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        url_path="request",
        permission_classes=[IsGMProfile],
    )
    def request_claim(self, request: Request) -> Response:
        """POST /api/assistant-gm-claims/request/ — an AGM requests to run a beat.

        Requires a GMProfile (enforced by IsGMProfile). Beat existence and
        agm_eligible validation handled by RequestClaimInputSerializer.
        Returns 201 with the claim on success.
        """
        from world.stories.services.assistant_gm import request_claim  # noqa: PLC0415

        ser = RequestClaimInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        claim = request_claim(
            beat=data["beat"],
            assistant_gm=request.user.gm_profile,
            framing_note=data["framing_note"],
        )
        return Response(AssistantGMClaimSerializer(claim).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="approve",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def approve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/approve/ — Lead GM approves the claim.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation handled by ApproveClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import approve_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = ApproveClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        updated = approve_claim(
            claim=claim,
            approver=request.user.gm_profile,
            framing_note=data.get("framing_note"),
        )
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="reject",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def reject(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/reject/ — Lead GM rejects the claim.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation handled by RejectClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import reject_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = RejectClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        updated = reject_claim(
            claim=claim,
            approver=request.user.gm_profile,
            note=data["note"],
        )
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="cancel",
        permission_classes=[IsClaimOwnerOrStaff],
    )
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/cancel/ — the AGM cancels their own claim.

        Status validation (must be REQUESTED) handled by CancelClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import cancel_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = CancelClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)

        updated = cancel_claim(claim=claim)
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="complete",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def complete(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/complete/ — Lead GM marks an approved claim done.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation (must be APPROVED) handled by CompleteClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import complete_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = CompleteClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)

        updated = complete_claim(claim=claim, completer=request.user.gm_profile)
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)


class SessionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for SessionRequest.

    Read: ReadOnlyModelViewSet (list + retrieve).
    State transitions: custom @action endpoints (Wave 11):
      POST /api/session-requests/{id}/create-event/ — create_event_from_session_request
      POST /api/session-requests/{id}/cancel/       — cancel_session_request
      POST /api/session-requests/{id}/resolve/      — resolve_session_request

    Wave 7 auto-creates requests; manual creation is admin-only.
    Read access: players with StoryParticipation, assigned/story-owning GMs, staff.
    """

    queryset = SessionRequest.objects.select_related(
        "episode__chapter__story",
        "event",
        "assigned_gm__account",
        "initiated_by_account",
    )
    serializer_class = SessionRequestSerializer
    permission_classes = [IsSessionRequestParticipantOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = SessionRequestFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[SessionRequest]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        filters_q = models.Q(
            episode__chapter__story__participants__character__db_account=self.request.user,
            episode__chapter__story__participants__is_active=True,
        ) | models.Q(episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assigned_gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="create-event",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def create_event(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/create-event/ — schedule a session by creating an Event.

        Bridges an OPEN SessionRequest to the events system. Status and host_persona
        FK validated by CreateEventFromSessionRequestInputSerializer.
        Returns 201 with the SessionRequest on success.
        """
        from world.stories.services.scheduling import (  # noqa: PLC0415
            create_event_from_session_request,
        )

        session_request = self.get_object()
        ser = CreateEventFromSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        create_event_from_session_request(
            session_request=session_request,
            name=data["name"],
            scheduled_real_time=data["scheduled_real_time"],
            host_persona=data["host_persona"],
            location_id=data["location_id"],
            description=data["description"],
            is_public=data["is_public"],
        )
        session_request.refresh_from_db()
        return Response(
            SessionRequestSerializer(session_request).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="cancel",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/cancel/ — cancel an OPEN session request.

        Status validation (must be OPEN) handled by CancelSessionRequestInputSerializer.
        Returns 200 with the updated SessionRequest.
        """
        from world.stories.services.scheduling import cancel_session_request  # noqa: PLC0415

        session_request = self.get_object()
        ser = CancelSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)

        updated = cancel_session_request(session_request=session_request)
        return Response(SessionRequestSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/resolve/ — mark a scheduled session as resolved.

        Status validation (must be SCHEDULED) handled by ResolveSessionRequestInputSerializer.
        Returns 200 with the updated SessionRequest.
        """
        from world.stories.services.scheduling import resolve_session_request  # noqa: PLC0415

        session_request = self.get_object()
        ser = ResolveSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)

        updated = resolve_session_request(session_request=session_request)
        return Response(SessionRequestSerializer(updated).data, status=status.HTTP_200_OK)


class BeatViewSet(viewsets.ModelViewSet):
    """ViewSet for Beat — includes all Phase 2 predicate config fields.

    Access delegated to episode story ownership (same as EpisodeViewSet).
    """

    queryset = Beat.objects.select_related(
        "episode__chapter__story",
        "required_achievement",
        "required_condition_template",
        "required_codex_entry",
        "referenced_story",
        "referenced_chapter",
        "referenced_episode",
    )
    serializer_class = BeatSerializer
    permission_classes = [IsBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BeatFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order", "created_at", "updated_at"]
    ordering = ["episode", "order"]

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="mark",
        permission_classes=[CanMarkBeat],
    )
    def mark(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/beats/{id}/mark/ — GM marks the outcome of a GM_MARKED beat.

        Lead GM, staff, or an AGM with an approved claim on this beat may call this.
        Wraps record_gm_marked_outcome. Returns 201 with BeatCompletion on success.
        """
        from world.stories.services.beats import record_gm_marked_outcome  # noqa: PLC0415

        beat = self.get_object()
        ser = MarkBeatInputSerializer(data=request.data, context={"beat": beat})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        completion = record_gm_marked_outcome(
            progress=data["progress"],
            beat=beat,
            outcome=data["outcome"],
            gm_notes=data["gm_notes"],
        )
        return Response(BeatCompletionSerializer(completion).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="contribute",
        permission_classes=[IsAccountOfCharacterSheet],
    )
    def contribute(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/beats/{id}/contribute/ — record a character contribution to an AGGREGATE beat.

        The requesting user must own the character_sheet (or be staff), validated
        by ContributeBeatInputSerializer. Wraps record_aggregate_contribution.
        Returns 201 with contribution on success.
        """
        from world.stories.services.beats import record_aggregate_contribution  # noqa: PLC0415

        beat = self.get_object()
        ser = ContributeBeatInputSerializer(
            data=request.data, context={"beat": beat, "request": request}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        contribution = record_aggregate_contribution(
            beat=beat,
            character_sheet=data["character_sheet"],
            points=data["points"],
            source_note=data["source_note"],
        )
        return Response(
            AggregateBeatContributionSerializer(contribution).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Phase 4 Wave 9: Author editor ViewSets
# ---------------------------------------------------------------------------


class TransitionViewSet(viewsets.ModelViewSet):
    """ViewSet for Transition — guarded episode graph edges.

    Read: any authenticated user (Lead GM, players, staff).
    Write (create/update/delete): Lead GM on the source episode's story, or staff.

    The source episode's story is resolved via source_episode -> chapter -> story ->
    primary_table.gm.
    """

    queryset = Transition.objects.select_related(
        "source_episode__chapter__story__primary_table",
        "target_episode",
    )
    serializer_class = TransitionSerializer
    permission_classes = [IsLeadGMOnTransitionStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TransitionFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order", "created_at"]
    ordering = ["source_episode", "order"]


class EpisodeProgressionRequirementViewSet(viewsets.ModelViewSet):
    """ViewSet for EpisodeProgressionRequirement.

    Records which beats (and required outcomes) must be satisfied before any
    outbound transition fires from an episode.

    Read: any authenticated user.
    Write: Lead GM on the episode's story, or staff.
    """

    queryset = EpisodeProgressionRequirement.objects.select_related(
        "episode__chapter__story__primary_table",
        "beat",
    )
    serializer_class = EpisodeProgressionRequirementSerializer
    permission_classes = [IsLeadGMOnEpisodeStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = EpisodeProgressionRequirementFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["id"]
    ordering = ["episode", "id"]


class TransitionRequiredOutcomeViewSet(viewsets.ModelViewSet):
    """ViewSet for TransitionRequiredOutcome.

    Records which beat outcomes must be satisfied for a specific transition to
    be eligible when the source episode is resolved.

    Read: any authenticated user.
    Write: Lead GM on the transition's source episode's story, or staff.
    """

    queryset = TransitionRequiredOutcome.objects.select_related(
        "transition__source_episode__chapter__story__primary_table",
        "beat",
    )
    serializer_class = TransitionRequiredOutcomeSerializer
    permission_classes = [IsLeadGMOnTransitionStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TransitionRequiredOutcomeFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["id"]
    ordering = ["transition", "id"]


# ---------------------------------------------------------------------------
# Wave 10: Dashboard APIViews
# ---------------------------------------------------------------------------


def _serialize_progress_entry(progress: AnyStoryProgress, scope: str) -> dict[str, Any]:
    """Build the dict shape shared by all three scope collectors in MyActiveStoriesView."""
    from world.stories.constants import StoryEpisodeStatus  # noqa: PLC0415

    story = progress.story
    episode = progress.current_episode
    summary = compute_story_status(progress)

    current_episode_id: int | None = episode.pk if episode is not None else None

    return {
        "story_id": story.pk,
        "story_title": story.title,
        "scope": scope,
        "current_episode_id": current_episode_id,
        "current_episode_title": summary.episode_title,
        "chapter_title": summary.chapter_title,
        "status": summary.status,
        "status_label": StoryEpisodeStatus(summary.status).label,
        "chapter_order": summary.chapter_order,
        "episode_order": summary.episode_order,
        "open_session_request_id": summary.open_session_request_id,
        "scheduled_event_id": summary.scheduled_event_id,
        "scheduled_real_time": summary.scheduled_real_time,
    }


def _collect_character_stories(account: AbstractBaseUser | AnonymousUser) -> list[dict[str, Any]]:
    """Return active CHARACTER-scope progress entries owned by this account."""
    qs = StoryProgress.objects.filter(
        story__character_sheet__character__db_account=account,
        is_active=True,
    ).select_related(
        "story",
        "current_episode",
        "current_episode__chapter",
    )
    return [_serialize_progress_entry(p, StoryScope.CHARACTER) for p in qs]


def _collect_group_stories(account: AbstractBaseUser | AnonymousUser) -> list[dict[str, Any]]:
    """Return active GROUP-scope progress entries for tables this account belongs to."""
    qs = (
        GroupStoryProgress.objects.filter(
            gm_table__memberships__persona__character_sheet__character__db_account=account,
            gm_table__memberships__left_at__isnull=True,
            is_active=True,
        )
        .select_related(
            "story",
            "current_episode",
            "current_episode__chapter",
        )
        .distinct()
    )
    return [_serialize_progress_entry(p, StoryScope.GROUP) for p in qs]


def _collect_global_stories(account: AbstractBaseUser | AnonymousUser) -> list[dict[str, Any]]:
    """Return active GLOBAL-scope progress entries where the account has a StoryParticipation."""
    qs = (
        GlobalStoryProgress.objects.filter(
            story__participants__character__db_account=account,
            story__participants__is_active=True,
            is_active=True,
        )
        .select_related(
            "story",
            "current_episode",
            "current_episode__chapter",
        )
        .distinct()
    )
    return [_serialize_progress_entry(p, StoryScope.GLOBAL) for p in qs]


class MyActiveStoriesView(APIView):
    """GET /api/stories/my-active/

    Returns the requesting account's active stories across all three scopes
    (CHARACTER / GROUP / GLOBAL), grouped by scope. Each entry carries a
    computed status line summarising what the player should do next.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return active stories for the authenticated account."""
        account = request.user
        character_stories = _collect_character_stories(account)
        group_stories = _collect_group_stories(account)
        global_stories = _collect_global_stories(account)
        return Response(
            {
                "character_stories": character_stories,
                "group_stories": group_stories,
                "global_stories": global_stories,
            }
        )


def _serialize_eligible_transitions(transitions: list) -> list[dict[str, Any]]:
    """Serialise eligible Transition objects for GM queue response."""
    return [{"transition_id": t.pk, "mode": t.mode} for t in transitions]


def _build_gm_queue_for_story(
    gm_profile: Any,
    story: Story,
    episodes_ready: list,
    pending_claims: list,
    assigned_requests: list,
) -> None:
    """Populate GM queue lists from a single story, dispatching on scope."""
    from world.stories.exceptions import ProgressionRequirementNotMetError  # noqa: PLC0415
    from world.stories.services.transitions import get_eligible_transitions  # noqa: PLC0415

    # Collect all active progress records for this story (may be multiple for GROUP).
    match story.scope:
        case StoryScope.CHARACTER:
            progress_qs: QuerySet[Any] = story.progress_records.filter(
                is_active=True
            ).select_related(
                "current_episode__chapter",
            )
            progress_type = StoryScope.CHARACTER
        case StoryScope.GROUP:
            progress_qs = story.group_progress_records.filter(is_active=True).select_related(
                "current_episode__chapter",
            )
            progress_type = StoryScope.GROUP
        case _:
            # GLOBAL scope: singleton progress record.
            try:
                global_progress = story.global_progress
            except GlobalStoryProgress.DoesNotExist:
                global_progress = None
            progress_qs = (
                [global_progress]
                if global_progress is not None and global_progress.is_active
                else []
            )
            progress_type = StoryScope.GLOBAL

    for progress in progress_qs:
        if progress.current_episode is None:
            continue
        try:
            eligible = get_eligible_transitions(progress)
        except ProgressionRequirementNotMetError:
            continue
        if not eligible:
            continue

        episode = progress.current_episode
        open_req = SessionRequest.objects.filter(
            episode=episode,
            status=SessionRequestStatus.OPEN,
        ).first()

        episodes_ready.append(
            {
                "story_id": story.pk,
                "story_title": story.title,
                "scope": story.scope,
                "episode_id": episode.pk,
                "episode_title": episode.title,
                "progress_type": progress_type,
                "progress_id": progress.pk,
                "eligible_transitions": _serialize_eligible_transitions(eligible),
                "open_session_request_id": open_req.pk if open_req else None,
            }
        )

    # AGM claims on this story that are pending approval.
    story_claims = AssistantGMClaim.objects.filter(
        beat__episode__chapter__story=story,
        status=AssistantClaimStatus.REQUESTED,
    ).select_related("beat", "assistant_gm__account")
    pending_claims.extend(
        {
            "claim_id": claim.pk,
            "beat_id": claim.beat_id,
            "beat_internal_description": claim.beat.internal_description,
            "story_title": story.title,
            "assistant_gm_id": claim.assistant_gm_id,
            "requested_at": claim.requested_at,
        }
        for claim in story_claims
    )

    # SessionRequests assigned to this GM on this story.
    story_assigned = SessionRequest.objects.filter(
        episode__chapter__story=story,
        assigned_gm=gm_profile,
        status__in=[SessionRequestStatus.OPEN, SessionRequestStatus.SCHEDULED],
    ).select_related("episode__chapter")
    assigned_requests.extend(
        {
            "session_request_id": sr.pk,
            "episode_id": sr.episode_id,
            "episode_title": sr.episode.title,
            "story_title": story.title,
            "status": sr.status,
            "event_id": sr.event_id,
        }
        for sr in story_assigned
    )


class GMQueueView(APIView):
    """GET /api/stories/gm-queue/

    Aggregates episodes ready to run across all stories where the requester
    is Lead GM, plus pending AGM claims and assigned SessionRequests.
    """

    permission_classes = [IsGMProfile]

    def get(self, request: Request) -> Response:
        """Return the GM's current work queue."""
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None

        episodes_ready: list[dict[str, Any]] = []
        pending_claims: list[dict[str, Any]] = []
        assigned_requests: list[dict[str, Any]] = []

        # Stories where this GMProfile is Lead GM (via primary_table.gm).
        lead_stories = Story.objects.filter(
            primary_table__gm=gm_profile,
            status="active",
        ).distinct()

        for story in lead_stories:
            _build_gm_queue_for_story(
                gm_profile,
                story,
                episodes_ready,
                pending_claims,
                assigned_requests,
            )

        return Response(
            {
                "episodes_ready_to_run": episodes_ready,
                "pending_agm_claims": pending_claims,
                "assigned_session_requests": assigned_requests,
            }
        )


class ExpireOverdueBeatsView(APIView):
    """POST /api/stories/expire-overdue-beats/

    Staff-only trigger that flips all UNSATISFIED beats with past deadlines
    to EXPIRED. Designed for manual triggering and cron hooks.
    Returns {"expired_count": N}.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request: Request) -> Response:
        """Expire all overdue beats and return the count."""
        from world.stories.services.beats import expire_overdue_beats  # noqa: PLC0415

        expired_count = expire_overdue_beats()
        return Response({"expired_count": expired_count}, status=status.HTTP_200_OK)


class StaffWorkloadView(APIView):
    """GET /api/stories/staff-workload/

    Staff-only cross-story metrics: per-GM queue depth, stale stories,
    stories at the authoring frontier, and aggregate counts.

    Performance: queries are straightforward for MVP. Consider caching
    the per-GM queue depth if the GMProfile/story count grows large.
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request: Request) -> Response:
        """Return cross-story workload metrics for staff."""
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.exceptions import ProgressionRequirementNotMetError  # noqa: PLC0415
        from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415
        from world.stories.services.transitions import get_eligible_transitions  # noqa: PLC0415

        # --- per-GM queue depth ---
        gm_profiles = (
            GMProfile.objects.select_related("account")
            .filter(
                tables__primary_stories__isnull=False,
            )
            .distinct()
        )

        per_gm_queue: list[dict[str, Any]] = []
        for gm in gm_profiles:
            lead_stories = Story.objects.filter(
                primary_table__gm=gm,
                status="active",
            )
            episodes_ready_count = 0
            for story in lead_stories:
                progress = get_active_progress_for_story(story)
                if progress is None or progress.current_episode is None:
                    continue
                try:
                    eligible = get_eligible_transitions(progress)
                except ProgressionRequirementNotMetError:
                    continue
                if eligible:
                    episodes_ready_count += 1

            pending_claims_count = AssistantGMClaim.objects.filter(
                beat__episode__chapter__story__primary_table__gm=gm,
                status=AssistantClaimStatus.REQUESTED,
            ).count()

            per_gm_queue.append(
                {
                    "gm_profile_id": gm.pk,
                    "gm_name": gm.account.username,
                    "episodes_ready": episodes_ready_count,
                    "pending_claims": pending_claims_count,
                }
            )

        # --- stale stories ---
        cutoff = timezone.now() - timezone.timedelta(days=STALE_STORY_DAYS)
        stale_qs = (
            list(
                StoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
            + list(
                GroupStoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
            + list(
                GlobalStoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
        )

        now = timezone.now()
        stale_stories: list[dict[str, Any]] = [
            {
                "story_id": row["story__id"],
                "story_title": row["story__title"],
                "last_advanced_at": row["last_advanced_at"],
                "days_stale": (now - row["last_advanced_at"]).days,
            }
            for row in stale_qs
        ]

        # --- stories at frontier (current_episode is None but active) ---
        frontier_char = list(
            StoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        frontier_group = list(
            GroupStoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        frontier_global = list(
            GlobalStoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        stories_at_frontier: list[dict[str, Any]] = [
            {
                "story_id": row["story__id"],
                "story_title": row["story__title"],
                "scope": row["story__scope"],
            }
            for row in frontier_char + frontier_group + frontier_global
        ]

        # --- aggregate counts ---
        pending_agm_count = AssistantGMClaim.objects.filter(
            status=AssistantClaimStatus.REQUESTED,
        ).count()

        open_session_req_count = SessionRequest.objects.filter(
            status=SessionRequestStatus.OPEN,
        ).count()

        counts_by_scope_qs = Story.objects.values("scope").annotate(count=Count("pk"))
        counts_by_scope: dict[str, int] = {row["scope"]: row["count"] for row in counts_by_scope_qs}

        return Response(
            {
                "per_gm_queue_depth": per_gm_queue,
                "stale_stories": stale_stories,
                "stories_at_frontier": stories_at_frontier,
                "pending_agm_claims_count": pending_agm_count,
                "open_session_requests_count": open_session_req_count,
                "counts_by_scope": counts_by_scope,
            }
        )
