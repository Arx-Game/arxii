"""API views for the relationships system."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Exists, OuterRef, Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from world.mechanics.models import ModifierTarget
from world.relationships.filters import RelationshipCapstoneFilter
from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    HybridRequirement,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipTier,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
    WriteupKudos,
)
from world.relationships.serializers import (
    CapstoneWriteSerializer,
    CharacterRelationshipListSerializer,
    CharacterRelationshipSerializer,
    DevelopmentWriteSerializer,
    FirstImpressionWriteSerializer,
    HybridRelationshipTypeSerializer,
    RedistributeWriteSerializer,
    RelationshipCapstoneSerializer,
    RelationshipConditionSerializer,
    RelationshipTrackSerializer,
    WriteupComplaintWriteSerializer,
    WriteupKudosWriteSerializer,
)


class RelationshipConditionViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related(
        Prefetch(
            "gates_modifiers",
            queryset=ModifierTarget.objects.all(),
            to_attr="cached_gates_modifiers",
        ),
    )
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RelationshipTrackViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship tracks with nested tiers."""

    queryset = RelationshipTrack.objects.prefetch_related(
        Prefetch(
            "tiers",
            queryset=RelationshipTier.objects.all(),
            to_attr="cached_tiers",
        ),
    )
    serializer_class = RelationshipTrackSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class HybridRelationshipTypeViewSet(ReadOnlyModelViewSet):
    """List and retrieve hybrid relationship types with nested requirements."""

    queryset = HybridRelationshipType.objects.prefetch_related(
        Prefetch(
            "requirements",
            queryset=HybridRequirement.objects.select_related("track"),
            to_attr="cached_requirements",
        ),
    )
    serializer_class = HybridRelationshipTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class CharacterRelationshipViewSet(ReadOnlyModelViewSet):
    """List and retrieve character relationships."""

    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["source", "target", "is_active", "is_pending", "is_soul_tether"]

    def get_queryset(self):  # type: ignore[override]
        """Return relationships with related data prefetched."""
        return CharacterRelationship.objects.select_related(
            "source",
            "source__character",
            "target",
            "target__character",
        ).prefetch_related(
            Prefetch(
                "track_progress",
                queryset=RelationshipTrackProgress.objects.select_related("track"),
                to_attr="cached_track_progress",
            ),
            Prefetch(
                "updates",
                queryset=RelationshipUpdate.objects.all(),
                to_attr="cached_updates",
            ),
            Prefetch(
                "conditions",
                queryset=RelationshipCondition.objects.all(),
                to_attr="cached_conditions",
            ),
        )

    def get_serializer_class(self):  # type: ignore[override]
        """Use list serializer for list action, full serializer for detail."""
        if self.action == "list":
            return CharacterRelationshipListSerializer
        return CharacterRelationshipSerializer


class RelationshipCapstoneViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet exposing the caller's RelationshipCapstone rows.

    Used by the frontend to populate the Soul Tether ritual perform form's
    capstone picker. The ``?other_character_sheet_id=`` filter narrows to
    capstones whose parent relationship involves a specific target character.
    """

    serializer_class = RelationshipCapstoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RelationshipCapstoneFilter

    def get_queryset(self) -> RelationshipCapstone.objects.__class__:  # type: ignore[override]
        """Return capstones authored by the caller's character sheets, newest first.

        Annotates ``kudos_count`` (total commendations) and ``viewer_has_kudosed``
        (whether this user has commended each capstone) on every row to avoid N+1
        queries when serializing the list.
        """
        user = self.request.user
        return (
            RelationshipCapstone.objects.filter(author__character__db_account=user)
            .select_related(
                "author",
                "author__character",
                "track",
                "relationship",
            )
            .annotate(
                kudos_count=Count("writeupkudos_set"),
                viewer_has_kudosed=Exists(
                    WriteupKudos.objects.filter(account_id=user.pk, capstone=OuterRef("pk"))
                ),
            )
            .order_by("-created_at")
        )


class RelationshipUpdateViewSet(GenericViewSet):
    """Write-only endpoints for relationship-building verbs.

    List/detail relationship state remains on CharacterRelationshipViewSet;
    this ViewSet only exposes the four mutation actions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = FirstImpressionWriteSerializer

    def get_serializer_class(self):  # type: ignore[override]
        """Return the write serializer matching the current action."""
        mapping = {
            "first_impression": FirstImpressionWriteSerializer,
            "develop": DevelopmentWriteSerializer,
            "capstone": CapstoneWriteSerializer,
            "redistribute": RedistributeWriteSerializer,
            "kudos": WriteupKudosWriteSerializer,
            "complaint": WriteupComplaintWriteSerializer,
        }
        return mapping.get(self.action, FirstImpressionWriteSerializer)

    def _resolve_target_sheet(self, target_persona_id: int):
        """Resolve a target persona ID to its CharacterSheet."""
        from world.scenes.models import Persona  # noqa: PLC0415

        return (
            Persona.objects.filter(pk=target_persona_id).select_related("character_sheet").first()
        )

    def _resolve_actor(self, request):
        """Return the caller's active puppet ObjectDB if they own its sheet."""
        actor = getattr(request.user, "puppet", None)  # noqa: GETATTR_LITERAL
        if actor is None:
            return None, "No active character."
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None, "No active character."
        if sheet.character.db_account_id != request.user.pk:
            return None, "No active character."
        return actor, ""

    def _resolve_track(self, track_id: int, label: str):
        """Resolve a track by pk; return ``(track, None)`` or ``(None, Response)``."""
        try:
            return RelationshipTrack.objects.get(pk=track_id), None
        except RelationshipTrack.DoesNotExist:
            return None, Response(
                {"success": False, "message": f"{label} track not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _build_kwargs(self, data: dict) -> tuple[dict | None, Response | None]:
        """Build action kwargs from validated serializer data.

        Returns ``(kwargs, None)`` on success or ``(None, error_response)`` if a
        referenced track cannot be resolved. impression/develop/capstone target a
        single ``track``; redistribute moves points between ``source_track`` and
        ``target_track`` instead.
        """
        kwargs: dict[str, object] = {
            "target_sheet": data["target_sheet"],
            "points": data["points"],
            "title": data["title"],
            "writeup": data["writeup"],
            "visibility": data["visibility"],
        }
        if "track_id" in data:  # noqa: STRING_LITERAL
            track, err = self._resolve_track(data["track_id"], "Relationship")
            if err is not None:
                return None, err
            kwargs["track"] = track
        if "coloring" in data:  # noqa: STRING_LITERAL
            kwargs["coloring"] = data["coloring"]
        if "xp_awarded" in data:  # noqa: STRING_LITERAL
            kwargs["xp_awarded"] = data["xp_awarded"]
        if "source_track_id" in data:  # noqa: STRING_LITERAL
            track, err = self._resolve_track(data["source_track_id"], "Source")
            if err is not None:
                return None, err
            kwargs["source_track"] = track
        if "target_track_id" in data:  # noqa: STRING_LITERAL
            track, err = self._resolve_track(data["target_track_id"], "Target")
            if err is not None:
                return None, err
            kwargs["target_track"] = track
        return kwargs, None

    def _run_action(self, request, action_class):
        """Validate input, resolve IDs, and run the relationship action."""
        actor, error = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"success": False, "message": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_persona = self._resolve_target_sheet(data["target_persona_id"])
        if target_persona is None:
            return Response(
                {"success": False, "message": "Target persona not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data["target_sheet"] = target_persona.character_sheet

        kwargs, err = self._build_kwargs(data)
        if err is not None:
            return err

        result = action_class().run(actor=actor, **kwargs)
        if not result.success:
            return Response(
                {"success": False, "message": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "success": True,
                "message": result.message,
                "data": result.data or {},
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def first_impression(self, request):
        """Record a first impression toward another character."""
        from actions.definitions.relationships import (  # noqa: PLC0415
            CreateFirstImpressionAction,
        )

        return self._run_action(request, CreateFirstImpressionAction)

    @action(detail=False, methods=["post"])
    def develop(self, request):
        """Solidify temporary points into permanent developed points."""
        from actions.definitions.relationships import (  # noqa: PLC0415
            CreateDevelopmentAction,
        )

        return self._run_action(request, CreateDevelopmentAction)

    @action(detail=False, methods=["post"])
    def capstone(self, request):
        """Record a monumental relationship capstone."""
        from actions.definitions.relationships import (  # noqa: PLC0415
            CreateCapstoneAction,
        )

        return self._run_action(request, CreateCapstoneAction)

    @action(detail=False, methods=["post"])
    def redistribute(self, request):
        """Move developed points between tracks in an existing relationship."""
        from actions.definitions.relationships import (  # noqa: PLC0415
            RedistributePointsAction,
        )

        return self._run_action(request, RedistributePointsAction)

    def _run_feedback_action(self, request, action_class):
        """Resolve actor, validate input, and dispatch a writeup-feedback action.

        Simpler than ``_run_action``: no target persona resolution or track
        building — the feedback actions only need ``actor`` + the validated
        serializer kwargs (``writeup_type``, ``writeup_id``, optional ``reason``).
        """
        actor, error = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"success": False, "message": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = action_class().run(actor=actor, **serializer.validated_data)
        if not result.success:
            return Response(
                {"success": False, "message": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "success": True,
                "message": result.message,
                "data": result.data or {},
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def kudos(self, request):
        """Commend a shared relationship writeup on behalf of its subject."""
        from actions.definitions.relationships import GiveWriteupKudosAction  # noqa: PLC0415

        return self._run_feedback_action(request, GiveWriteupKudosAction)

    @action(detail=False, methods=["post"])
    def complaint(self, request):
        """File a bad-faith-RP complaint against a writeup for staff triage."""
        from actions.definitions.relationships import FileWriteupComplaintAction  # noqa: PLC0415

        return self._run_feedback_action(request, FileWriteupComplaintAction)
