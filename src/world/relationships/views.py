"""API views for the relationships system."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from world.mechanics.models import ModifierTarget
from world.relationships.constants import UpdateVisibility
from world.relationships.filters import RelationshipCapstoneFilter, RelationshipUpdateFilter
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
    RelationshipUpdateSerializer,
    WriteupComplaintWriteSerializer,
    WriteupKudosWriteSerializer,
)

NO_ACTIVE_CHARACTER_MESSAGE = "No active character."


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
        """Return relationships the caller may read, with related data prefetched.

        Numeric relationship state (tracks, affection, tiers) is author-private:
        scoped to rows where ``source`` belongs to one of the caller's own
        characters, via a current (``end_date__isnull=True``) ``RosterTenure``
        join — mirroring ``RelationshipUpdateViewSet.get_queryset``'s tenure
        join rather than Evennia's live-puppet ``db_account`` field, so an
        owner browsing while not currently puppeting that character still sees
        their own outbound rows. ``is_soul_tether=True`` rows are a ratified
        carve-out and stay universally readable regardless of ownership: the
        Soul Tether panel rendered on a *foreign* character's sheet depends on
        being able to read the tether row (see ADR-0117).
        """
        user = self.request.user
        return (
            CharacterRelationship.objects.filter(
                Q(
                    source__roster_entry__tenures__player_data__account=user,
                    source__roster_entry__tenures__end_date__isnull=True,
                )
                | Q(is_soul_tether=True)
            )
            .distinct()
            .select_related(
                "source",
                "source__character",
                "target",
                "target__character",
            )
            .prefetch_related(
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


class RelationshipUpdateViewSet(ListModelMixin, GenericViewSet):
    """Mutation actions for relationship-building verbs, plus a narrow list route.

    Detail/browsing of relationship state in general remains on
    CharacterRelationshipViewSet; the ``list`` action here exists only to feed
    the commend button on the requesting user's own writeups-about-them (the
    subject side of ``give_writeup_kudos``'s rule) — it is not a general
    writeup browser. Scoped to writeups where the caller's character is the
    parent relationship's ``target`` (the writeup's commendable subject) and
    visibility is SHARED or PUBLIC; PRIVATE and GOSSIP writeups never appear
    here regardless of subject. Subject eligibility is tenure-based (current,
    un-ended ``RosterTenure``, mirroring ``get_account_for_character``), not
    Evennia's live-puppet ``db_account`` field, so a subject browsing while
    not currently puppeting the character still sees writeups they can
    legally commend. ``?subject_character=<CharacterSheet pk>`` narrows to one
    owned character sheet (see ``RelationshipUpdateFilter``) for accounts with
    several owned characters.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = FirstImpressionWriteSerializer
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RelationshipUpdateFilter

    def get_serializer_class(self):  # type: ignore[override]
        """Return the write serializer matching the current action."""
        mapping = {
            "list": RelationshipUpdateSerializer,
            "first_impression": FirstImpressionWriteSerializer,
            "develop": DevelopmentWriteSerializer,
            "capstone": CapstoneWriteSerializer,
            "redistribute": RedistributeWriteSerializer,
            "kudos": WriteupKudosWriteSerializer,
            "complaint": WriteupComplaintWriteSerializer,
        }
        return mapping.get(self.action, FirstImpressionWriteSerializer)

    def get_queryset(self):  # type: ignore[override]
        """Return SHARED/PUBLIC writeups about the caller's tenure-owned subject character(s).

        Subject eligibility mirrors ``world.roster.selectors.get_account_for_character``'s
        tenure join — a current (``end_date__isnull=True``) ``RosterTenure`` — rather than
        the live-puppet ``db_account`` field: a subject browsing their sheet while not
        currently puppeting that character must still see (and be able to commend)
        writeups about them.

        The eligible subject pks are resolved via a separate ``.distinct()`` lookup and
        applied to the annotated queryset with ``pk__in`` rather than joining ``tenures``
        directly alongside the ``Count``/``Exists`` annotations — joining the to-many
        ``tenures`` relation on the same query as those aggregates would risk inflating
        ``kudos_count`` if a character ever had more than one current tenure row (should
        not happen, but isn't DB-enforced).
        """
        user = self.request.user
        eligible_ids = (
            RelationshipUpdate.objects.filter(
                relationship__target__roster_entry__tenures__player_data__account=user,
                relationship__target__roster_entry__tenures__end_date__isnull=True,
            )
            .values_list("pk", flat=True)
            .distinct()
        )
        return (
            RelationshipUpdate.objects.filter(
                pk__in=eligible_ids,
                visibility__in=[UpdateVisibility.SHARED, UpdateVisibility.PUBLIC],
            )
            .select_related("author", "author__character", "track", "relationship")
            .annotate(
                kudos_count=Count("writeupkudos_set"),
                viewer_has_kudosed=Exists(
                    WriteupKudos.objects.filter(account_id=user.pk, update=OuterRef("pk"))
                ),
            )
            .order_by("-created_at")
        )

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
            return None, NO_ACTIVE_CHARACTER_MESSAGE
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None, NO_ACTIVE_CHARACTER_MESSAGE
        if sheet.character.db_account_id != request.user.pk:
            return None, NO_ACTIVE_CHARACTER_MESSAGE
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
