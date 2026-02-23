from datetime import timedelta
from http import HTTPMethod
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.scenes.filters import PersonaFilter, SceneFilter, SceneMessageFilter
from world.scenes.models import (
    Persona,
    Scene,
    SceneMessage,
    SceneMessageReaction,
    SceneParticipation,
)
from world.scenes.pagination import (
    PersonaPagination,
    SceneMessageCursorPagination,
    ScenePagination,
)
from world.scenes.permissions import (
    CanCreateMessageInScene,
    CanCreatePersonaInScene,
    IsMessageSenderOrStaff,
    IsSceneGMOrOwnerOrStaff,
    IsSceneOwnerOrStaff,
    ReadOnlyOrSceneParticipant,
)
from world.scenes.serializers import (
    PersonaSerializer,
    SceneDetailSerializer,
    SceneListSerializer,
    SceneMessageReactionSerializer,
    SceneMessageSerializer,
    ScenesSpotlightSerializer,
)
from world.scenes.services import broadcast_scene_message


class SceneViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing scenes
    """

    queryset = Scene.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_class = SceneFilter
    pagination_class = ScenePagination
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self) -> QuerySet[Scene]:
        queryset = super().get_queryset()
        if self.action == "list":
            user = self.request.user
            if user.is_authenticated:
                if user.is_staff:
                    return queryset
                return queryset.filter(Q(is_public=True) | Q(participants=user))
            return queryset.filter(is_public=True)
        return queryset

    def get_serializer_class(self) -> type[BaseSerializer[Scene]]:
        if self.action == "list":
            return SceneListSerializer
        return SceneDetailSerializer

    def perform_create(self, serializer: BaseSerializer[Scene]) -> None:
        location = serializer.validated_data.get("location")
        name = serializer.validated_data.get("name")
        if location and Scene.objects.filter(location=location, is_active=True).exists():
            raise serializers.ValidationError(
                {"location": "An active scene already exists in this location."},
            )

        if not name:
            location_name = "unknown"
            if location is not None:
                try:
                    location_name = location.db_key
                except AttributeError:
                    location_name = "unknown"
            base_name = (
                f"{self.request.user.username} scene at {location_name} on {timezone.now().date()}"
            )
        else:
            base_name = name

        unique_name = base_name
        counter = 2
        while Scene.objects.filter(name=unique_name).exists():
            unique_name = f"{base_name} ({counter})"
            counter += 1

        scene = serializer.save(name=unique_name)
        SceneParticipation.objects.get_or_create(
            scene=scene,
            account=self.request.user,
            defaults={"is_owner": True},
        )
        broadcast_scene_message(scene, "start")

    def perform_update(self, serializer: BaseSerializer[Scene]) -> None:
        scene = serializer.save()
        broadcast_scene_message(scene, "update")

    def get_permissions(self) -> list[BasePermission]:
        """
        Instantiate and return the list of permissions required for this view.
        """
        if self.action == "finish":
            # Only scene owners/GMs or staff can finish scenes
            permission_classes = [IsSceneGMOrOwnerOrStaff]
        elif self.action in ["update", "partial_update", "destroy"]:
            # Only scene owners or staff can modify/delete scenes
            permission_classes = [IsSceneOwnerOrStaff]
        elif self.action == "retrieve":
            # For retrieving scenes, use both authentication and
            # private scene access checks
            permission_classes = [IsAuthenticatedOrReadOnly, ReadOnlyOrSceneParticipant]
        else:
            # Default permissions for list, create, spotlight
            permission_classes = self.permission_classes

        return [permission() for permission in permission_classes]

    @action(detail=False, methods=[HTTPMethod.GET])
    def spotlight(self, request: Request) -> Response:
        """
        Endpoint that matches frontend expectations: /api/scenes/spotlight/
        Returns in_progress and recent scenes
        """
        # Get active scenes
        active_scenes = Scene.objects.filter(is_active=True, is_public=True)[:10]

        # Get recently finished scenes (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_scenes = Scene.objects.filter(
            is_active=False,
            is_public=True,
            date_finished__gte=seven_days_ago,
        ).order_by("-date_finished")[:10]

        # Prepare data for serializer
        data = {"active_scenes": active_scenes, "recent_scenes": recent_scenes}

        serializer = ScenesSpotlightSerializer(data)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def finish(self, request: Request, pk: int | None = None) -> Response:
        """
        Finish an active scene
        """
        scene = self.get_object()
        if scene.is_finished:
            return Response(
                {"error": "Scene is already finished"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scene.finish_scene()
        broadcast_scene_message(scene, "end")
        serializer = self.get_serializer(scene)
        return Response(serializer.data)


class PersonaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing personas within scenes
    """

    serializer_class = PersonaSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PersonaFilter
    pagination_class = PersonaPagination
    permission_classes = [CanCreatePersonaInScene]

    def get_queryset(self) -> QuerySet[Persona]:
        return Persona.objects.select_related(
            "participation__scene",
            "participation__account",
            "character__roster_entry",
        ).order_by("created_at")


class SceneMessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing messages within scenes with pagination and filtering
    """

    serializer_class = SceneMessageSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SceneMessageFilter
    pagination_class = SceneMessageCursorPagination
    permission_classes = [CanCreateMessageInScene]

    def get_queryset(self) -> QuerySet[SceneMessage]:
        return SceneMessage.objects.select_related(
            "scene",
            "persona",
            "persona__participation__account",
            "persona__character__roster_entry",
            "supplemental_data",
        ).prefetch_related("receivers")

    def get_permissions(self) -> list[BasePermission]:
        """
        Instantiate and return the list of permissions required for this view.
        """
        if self.action in ["update", "partial_update", "destroy"]:
            # Only message sender or staff can modify/delete messages
            permission_classes = [IsMessageSenderOrStaff]
        else:
            # Default permissions for list, retrieve, create
            permission_classes = self.permission_classes

        return [permission() for permission in permission_classes]

    def perform_create(self, serializer: BaseSerializer[SceneMessage]) -> None:
        """Ensure the scene is still active when creating messages."""
        persona_id = serializer.validated_data.get("persona_id")
        if persona_id:
            try:
                persona = Persona.objects.select_related("participation__scene").get(
                    id=persona_id,
                )
                if not persona.participation.scene.is_active:
                    raise serializers.ValidationError(
                        {"scene": "Cannot create messages in a finished scene."},
                    )
            except Persona.DoesNotExist:
                pass  # Serializer will handle missing persona
        serializer.save()


class SceneMessageReactionViewSet(viewsets.ModelViewSet):
    """ViewSet for adding or removing reactions on scene messages."""

    serializer_class = SceneMessageReactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["post", "delete"]

    def get_queryset(self) -> QuerySet[SceneMessageReaction]:
        return SceneMessageReaction.objects.filter(account=self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle a reaction on or off for the authenticated user."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        deleted, _ = SceneMessageReaction.objects.filter(
            message=data["message"],
            account=request.user,
            emoji=data["emoji"],
        ).delete()
        if deleted:
            return Response({"detail": "Reaction removed."}, status=status.HTTP_200_OK)
        serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )
