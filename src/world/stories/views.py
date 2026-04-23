from http import HTTPMethod

from django.db import models
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.stories.filters import (
    AggregateBeatContributionFilter,
    AssistantGMClaimFilter,
    ChapterFilter,
    EpisodeFilter,
    EpisodeSceneFilter,
    GlobalStoryProgressFilter,
    GroupStoryProgressFilter,
    PlayerTrustFilter,
    SessionRequestFilter,
    StoryFeedbackFilter,
    StoryFilter,
    StoryParticipationFilter,
)
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    Chapter,
    Episode,
    EpisodeScene,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    SessionRequest,
    Story,
    StoryFeedback,
    StoryParticipation,
)
from world.stories.pagination import (
    LargeResultsSetPagination,
    SmallResultsSetPagination,
    StandardResultsSetPagination,
)
from world.stories.permissions import (
    CanParticipateInStory,
    IsBeatStoryOwnerOrStaff,
    IsChapterStoryOwnerOrStaff,
    IsClaimantOrLeadGMOrStaff,
    IsContributorOrLeadGMOrStaff,
    IsEpisodeStoryOwnerOrStaff,
    IsGlobalProgressReadableOrStaff,
    IsGroupProgressMemberOrStaff,
    IsParticipationOwnerOrStoryOwnerOrStaff,
    IsPlayerTrustOwnerOrStaff,
    IsReviewerOrStoryOwnerOrStaff,
    IsSessionRequestParticipantOrStaff,
    IsStoryOwnerOrStaff,
)
from world.stories.serializers import (
    AggregateBeatContributionSerializer,
    AssistantGMClaimSerializer,
    BeatSerializer,
    ChapterCreateSerializer,
    ChapterDetailSerializer,
    ChapterListSerializer,
    EpisodeCreateSerializer,
    EpisodeDetailSerializer,
    EpisodeListSerializer,
    EpisodeSceneSerializer,
    GlobalStoryProgressSerializer,
    GroupStoryProgressSerializer,
    PlayerTrustSerializer,
    SessionRequestSerializer,
    StoryCreateSerializer,
    StoryDetailSerializer,
    StoryFeedbackCreateSerializer,
    StoryFeedbackSerializer,
    StoryListSerializer,
    StoryParticipationSerializer,
)


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

        participation = StoryParticipation.objects.create(
            story=story,
            character_id=character_id,
            participation_level=participation_level,
        )

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
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        gm_profile = getattr(self.request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
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
    """Read-only ViewSet for AssistantGMClaim.

    State transitions go through service-backed action endpoints (Wave 11).
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
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        gm_profile = getattr(self.request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        filters_q = models.Q(beat__episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assistant_gm=gm_profile)
        return qs.filter(filters_q).distinct()


class SessionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for SessionRequest.

    Wave 7 auto-creates requests; manual creation is admin-only.
    State transitions go through service-backed action endpoints (Wave 11).
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
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        gm_profile = getattr(self.request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        filters_q = models.Q(
            episode__chapter__story__participants__character__db_account=self.request.user,
            episode__chapter__story__participants__is_active=True,
        ) | models.Q(episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assigned_gm=gm_profile)
        return qs.filter(filters_q).distinct()


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
    filterset_class = None
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order", "created_at", "updated_at"]
    ordering = ["episode", "order"]
