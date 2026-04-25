from datetime import timedelta
from http import HTTPMethod

from django.db.models import Q, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import BasePermission, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.fatigue.tasks import process_deferred_fatigue_resets
from world.progression.services.scene_rewards import on_scene_finished
from world.scenes.constants import SceneAction, ScenePrivacyMode
from world.scenes.filters import (
    PersonaFilter,
    SceneFilter,
    SceneSummaryRevisionFilter,
)
from world.scenes.models import (
    Persona,
    Scene,
    SceneParticipation,
    SceneSummaryRevision,
)
from world.scenes.pagination import (
    PersonaPagination,
    ScenePagination,
)
from world.scenes.permissions import (
    CanCreatePersonaInScene,
    IsSceneGMOrOwnerOrStaff,
    IsSceneOwnerOrStaff,
    ReadOnlyOrSceneParticipant,
)
from world.scenes.serializers import (
    PersonaSerializer,
    SceneDetailSerializer,
    SceneListSerializer,
    ScenesSpotlightSerializer,
    SceneSummaryRevisionSerializer,
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
                return queryset.filter(
                    Q(privacy_mode=ScenePrivacyMode.PUBLIC) | Q(participants=user),
                )
            return queryset.filter(privacy_mode=ScenePrivacyMode.PUBLIC)
        return queryset

    def get_serializer_class(self) -> type[BaseSerializer[Scene]]:
        if self.action == "list":
            return SceneListSerializer
        return SceneDetailSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

        try:
            return super().create(request, *args, **kwargs)
        except ProtagonismLockedError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)

    def perform_create(self, serializer: BaseSerializer[Scene]) -> None:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

        # Raise if the requesting account's active character sheet is protagonism-locked.
        try:
            active_sheet = CharacterSheet.objects.get(
                roster_entry__tenures__player_data__account=self.request.user,
                roster_entry__tenures__end_date__isnull=True,
            )
            if active_sheet.is_protagonism_locked:
                raise ProtagonismLockedError
        except CharacterSheet.DoesNotExist:
            pass  # No active sheet — allow the scene to proceed

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
        broadcast_scene_message(scene, SceneAction.START)

    def perform_update(self, serializer: BaseSerializer[Scene]) -> None:
        instance = self.get_object()
        if (
            instance.privacy_mode == ScenePrivacyMode.EPHEMERAL
            and serializer.validated_data.get("privacy_mode", instance.privacy_mode)
            != ScenePrivacyMode.EPHEMERAL
        ):
            raise serializers.ValidationError(
                {"privacy_mode": "Cannot change privacy mode of an ephemeral scene."},
            )
        scene = serializer.save()
        broadcast_scene_message(scene, SceneAction.UPDATE)

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
        active_scenes = Scene.objects.filter(
            is_active=True,
            privacy_mode=ScenePrivacyMode.PUBLIC,
        )[:10]

        # Get recently finished scenes (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_scenes = Scene.objects.filter(
            is_active=False,
            privacy_mode=ScenePrivacyMode.PUBLIC,
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
        on_scene_finished(scene)
        participant_account_ids = set(scene.participations.values_list("account_id", flat=True))
        process_deferred_fatigue_resets(participant_account_ids)
        broadcast_scene_message(scene, SceneAction.END)
        serializer = self.get_serializer(scene)
        return Response(serializer.data)


class PersonaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing personas within scenes
    """

    serializer_class = PersonaSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = PersonaFilter
    search_fields = ["name"]
    pagination_class = PersonaPagination
    permission_classes = [CanCreatePersonaInScene]

    def get_queryset(self) -> QuerySet[Persona]:
        return Persona.objects.select_related(
            "character_sheet",
            "character_sheet__roster_entry",
        ).order_by("created_at")


class SceneSummaryRevisionViewSet(viewsets.ModelViewSet):
    """ViewSet for listing and creating scene summary revisions.

    Only participants of ephemeral scenes can submit summary revisions.
    """

    serializer_class = SceneSummaryRevisionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SceneSummaryRevisionFilter
    pagination_class = ScenePagination
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self) -> QuerySet[SceneSummaryRevision]:
        user = self.request.user
        return (
            SceneSummaryRevision.objects.filter(
                scene__participations__account=user,
            )
            .select_related("persona")
            .order_by("timestamp")
            .distinct()
        )
