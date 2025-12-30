from http import HTTPMethod

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from world.stories.filters import (
    ChapterFilter,
    EpisodeFilter,
    EpisodeSceneFilter,
    PlayerTrustFilter,
    StoryFeedbackFilter,
    StoryFilter,
    StoryParticipationFilter,
)
from world.stories.models import (
    Chapter,
    Episode,
    EpisodeScene,
    PlayerTrust,
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
    IsChapterStoryOwnerOrStaff,
    IsEpisodeStoryOwnerOrStaff,
    IsParticipationOwnerOrStoryOwnerOrStaff,
    IsPlayerTrustOwnerOrStaff,
    IsReviewerOrStoryOwnerOrStaff,
    IsStoryOwnerOrStaff,
)
from world.stories.serializers import (
    ChapterCreateSerializer,
    ChapterDetailSerializer,
    ChapterListSerializer,
    EpisodeCreateSerializer,
    EpisodeDetailSerializer,
    EpisodeListSerializer,
    EpisodeSceneSerializer,
    PlayerTrustSerializer,
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

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return StoryListSerializer
        if self.action == "create":
            return StoryCreateSerializer
        return StoryDetailSerializer

    def perform_create(self, serializer):
        """Set the creator as an owner when creating a story"""
        story = serializer.save()
        story.owners.add(self.request.user)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[CanParticipateInStory])
    def apply_to_participate(self, request, pk=None):
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
    def participants(self, request, pk=None):
        """Get all participants for a story"""
        story = self.get_object()
        participants = story.participants.filter(is_active=True)
        serializer = StoryParticipationSerializer(participants, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET])
    def chapters(self, request, pk=None):
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

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return ChapterListSerializer
        if self.action == "create":
            return ChapterCreateSerializer
        return ChapterDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def episodes(self, request, pk=None):
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

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return EpisodeListSerializer
        if self.action == "create":
            return EpisodeCreateSerializer
        return EpisodeDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def scenes(self, request, pk=None):
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
    ordering_fields = ["order", "connection_to_next"]
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
    def my_trust(self, request):
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

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "create":
            return StoryFeedbackCreateSerializer
        return StoryFeedbackSerializer

    def perform_create(self, serializer):
        """Set the reviewer as the current user when creating feedback"""
        serializer.save(reviewer=self.request.user)

    @action(detail=False, methods=[HTTPMethod.GET])
    def my_feedback(self, request):
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
    def feedback_given(self, request):
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
