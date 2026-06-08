from datetime import timedelta
from http import HTTPMethod

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
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
    Interaction,
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
from world.societies.renown_serializers import (
    RenownCardSerializer,
    RenownSerializer,
    build_renown_card_payload,
    build_renown_payload,
)
from world.societies.spread_serializers import (
    DeedStorySerializer,
    SaveDeedStoryInputSerializer,
    SpreadableDeedSerializer,
    SpreadInputSerializer,
    SpreadResultSerializer,
    SpreadSpecializationSerializer,
)


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
        # Prefetch interactions and their personas so list/detail serializers
        # can derive participants/personas from the cached list rather than
        # firing a fresh per-scene Persona query inside SerializerMethodField.
        # The persona/participant serializers walk
        # persona.character_sheet.roster_entry, then read
        # entry.character_sheet.character.db_key — the second character_sheet
        # hop hits the SharedMemoryModel identity map for free, so we only
        # need to chain as far as roster_entry plus the character ObjectDB.
        interactions_prefetch = Prefetch(
            "interactions",
            queryset=Interaction.objects.select_related(
                "persona__character_sheet__character",
                "persona__character_sheet__roster_entry",
                "persona__thumbnail",
            ),
            to_attr="cached_interactions",
        )
        queryset = (
            super().get_queryset().order_by("-date_started").prefetch_related(interactions_prefetch)
        )
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
        # Spotlight reuses SceneListSerializer, so the same prefetch is
        # required to keep get_participants from firing a per-scene
        # Persona query.
        interactions_prefetch = Prefetch(
            "interactions",
            queryset=Interaction.objects.select_related(
                "persona__character_sheet__character",
                "persona__character_sheet__roster_entry",
                "persona__thumbnail",
            ),
            to_attr="cached_interactions",
        )

        # Get active scenes
        active_scenes = Scene.objects.filter(
            is_active=True,
            privacy_mode=ScenePrivacyMode.PUBLIC,
        ).prefetch_related(interactions_prefetch)[:10]

        # Get recently finished scenes (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_scenes = (
            Scene.objects.filter(
                is_active=False,
                privacy_mode=ScenePrivacyMode.PUBLIC,
                date_finished__gte=seven_days_ago,
            )
            .order_by("-date_finished")
            .prefetch_related(interactions_prefetch)[:10]
        )

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
        # Exclude OOC system/narrator identities (e.g. the combat Narrator)
        # from the persona picker; their authored interactions still display.
        return (
            Persona.objects.select_related(
                "character_sheet",
                "character_sheet__roster_entry",
                "thumbnail",
            )
            .filter(is_system=False)
            .order_by("created_at")
        )

    @extend_schema(responses=RenownSerializer, tags=["personas"])
    @action(detail=True, methods=[HTTPMethod.GET])
    def renown(self, request: Request, pk: int | None = None) -> Response:
        """#676 Phase G — Read-only renown payload for the renown tab.

        Returns four prestige axes + total, fame buffer + tier metadata,
        per-society reputation (named tier labels, never numeric values),
        and the persona's recent deeds.

        Writes happen through the event-firing services (fire_renown_award
        etc.), not this endpoint.
        """
        persona = self.get_object()
        payload = build_renown_payload(persona)
        serializer = RenownSerializer(payload)
        return Response(serializer.data)

    @extend_schema(responses=SpreadableDeedSerializer(many=True), tags=["personas"])
    @action(detail=True, methods=[HTTPMethod.GET], url_path="spreadable-deeds")
    def spreadable_deeds(self, request: Request, pk: int | None = None) -> Response:
        """#745 — Deeds this persona may spread (societies_aware ∩ memberships)."""
        from world.societies.spread_services import get_spreadable_deeds  # noqa: PLC0415

        persona = self.get_object()
        deeds = get_spreadable_deeds(persona)
        return Response(SpreadableDeedSerializer(deeds, many=True).data)

    @extend_schema(responses=SpreadSpecializationSerializer(many=True), tags=["personas"])
    @action(detail=False, methods=[HTTPMethod.GET], url_path="spread-specializations")
    def spread_specializations(self, request: Request) -> Response:
        """#745 — Performance specializations a teller may optionally apply."""
        from world.societies.spread_services import get_spread_specializations  # noqa: PLC0415

        specs = get_spread_specializations()
        return Response(SpreadSpecializationSerializer(specs, many=True).data)

    @extend_schema(
        request=SpreadInputSerializer, responses=SpreadResultSerializer, tags=["personas"]
    )
    @action(detail=True, methods=[HTTPMethod.POST])
    def spread(self, request: Request, pk: int | None = None) -> Response:  # noqa: PLR0911
        """#745 — Spread a tale: resolve an area 'Spread a Tale' action for this persona."""
        from django.core.exceptions import ValidationError  # noqa: PLC0415
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.locations.activity_services import room_activity_band  # noqa: PLC0415
        from world.scenes.action_services import create_and_resolve_area_action  # noqa: PLC0415
        from world.scenes.models import Scene  # noqa: PLC0415
        from world.societies.models import LegendEntry  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            SPREAD_TALE_ACTION_KEY,
            get_or_create_spread_a_tale_template,
            get_spread_specializations,
            get_spreadable_deeds,
            spread_check_modifiers,
        )

        persona = self.get_object()
        if not self._account_controls_persona(request, persona):
            return Response(
                {"detail": "You do not control this persona."},
                status=status.HTTP_403_FORBIDDEN,
            )

        input_serializer = SpreadInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        scene = get_object_or_404(Scene, pk=data["scene"])
        if not scene.participants.filter(pk=request.user.pk).exists():
            return Response(
                {"detail": "You are not a participant in that scene."},
                status=status.HTTP_403_FORBIDDEN,
            )
        deed = get_object_or_404(LegendEntry, pk=data["deed"])
        if not get_spreadable_deeds(persona).filter(pk=deed.pk).exists():
            return Response(
                {"detail": "This persona cannot spread that deed."},
                status=status.HTTP_403_FORBIDDEN,
            )

        specialization = None
        specialization_id = data.get("specialization")
        if specialization_id:
            from world.skills.models import Specialization  # noqa: PLC0415

            valid_ids = set(get_spread_specializations().values_list("pk", flat=True))
            if specialization_id not in valid_ids:
                return Response(
                    {"detail": "That form can't be used to spread a tale."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            specialization = Specialization.objects.get(pk=specialization_id)
        extra_modifiers = spread_check_modifiers(persona.character_sheet.character, specialization)

        template = get_or_create_spread_a_tale_template()
        try:
            result = create_and_resolve_area_action(
                scene=scene,
                initiator_persona=persona,
                action_template=template,
                action_key=SPREAD_TALE_ACTION_KEY,
                pose_text=data["pose_text"],
                effort_level=data["effort_level"],
                spread_deed_target=deed,
                extra_modifiers=extra_modifiers,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            # e.g. the deed was deactivated between eligibility and resolution.
            return Response(
                {"detail": "The tale could not be spread right now."},
                status=status.HTTP_409_CONFLICT,
            )

        main = result.action_resolution.main_result
        outcome = main.check_result.outcome_name if main and main.check_result else "Unknown"
        band = room_activity_band(scene.location).label
        payload = {"resolved": True, "outcome": outcome, "band": band}
        return Response(SpreadResultSerializer(payload).data)

    def _account_controls_persona(self, request: Request, persona: Persona) -> bool:
        """True when the requesting account currently tenures this persona."""
        return Persona.objects.filter(
            pk=persona.pk,
            character_sheet__roster_entry__tenures__player_data__account=request.user,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
        ).exists()

    @extend_schema(responses=DeedStorySerializer(many=True), tags=["personas"])
    @action(detail=True, methods=[HTTPMethod.GET], url_path="deed-stories")
    def deed_stories(self, request: Request, pk: int | None = None) -> Response:
        """#745 Phase 4 — Written accounts of a deed this persona knows of.

        Requires ``?deed=<id>`` and that the persona's societies are aware of
        the deed (same awareness gate as spreading), so lore about unknown
        deeds isn't leaked.
        """
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.societies.models import LegendEntry  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            get_deed_stories,
            get_spreadable_deeds,
        )

        persona = self.get_object()
        deed_id = request.query_params.get("deed")  # noqa: USE_FILTERSET
        if not deed_id:
            return Response(
                {"detail": "A 'deed' query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deed = get_object_or_404(LegendEntry, pk=deed_id)
        if not get_spreadable_deeds(persona).filter(pk=deed.pk).exists():
            return Response(
                {"detail": "This persona is not aware of that deed."},
                status=status.HTTP_403_FORBIDDEN,
            )
        stories = get_deed_stories(deed)
        return Response(DeedStorySerializer(stories, many=True).data)

    @extend_schema(
        request=SaveDeedStoryInputSerializer, responses=DeedStorySerializer, tags=["personas"]
    )
    @action(detail=True, methods=[HTTPMethod.POST], url_path="deed-story")
    def deed_story(self, request: Request, pk: int | None = None) -> Response:
        """#745 Phase 4 — Save (or replace) this persona's account of a deed.

        Gated on persona control + awareness of the deed. One account per
        (deed, author); re-saving overwrites the prior text.
        """
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.societies.models import LegendEntry  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            get_spreadable_deeds,
            save_deed_story,
        )

        persona = self.get_object()
        if not self._account_controls_persona(request, persona):
            return Response(
                {"detail": "You do not control this persona."},
                status=status.HTTP_403_FORBIDDEN,
            )
        input_serializer = SaveDeedStoryInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        deed = get_object_or_404(LegendEntry, pk=data["deed"])
        if not get_spreadable_deeds(persona).filter(pk=deed.pk).exists():
            return Response(
                {"detail": "This persona is not aware of that deed."},
                status=status.HTTP_403_FORBIDDEN,
            )
        story = save_deed_story(author_persona=persona, deed=deed, text=data["text"])
        return Response(DeedStorySerializer(story).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=RenownCardSerializer,
        tags=["personas"],
        parameters=[
            OpenApiParameter(
                name="viewer_persona",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "PK of the viewer's currently-presented persona. Drives "
                    "deeds + reputation filtering. Omit for the anonymous "
                    "view (tier label only)."
                ),
            ),
        ],
    )
    @action(detail=True, methods=[HTTPMethod.GET], url_path="renown-card")
    def renown_card(self, request: Request, pk: int | None = None) -> Response:
        """#744 — Limited renown view of this persona for a foreign viewer.

        Surfaces only what the viewer's persona's societies are aware
        of: fame tier label, deeds the viewer's societies have heard
        about, reputation rows for the viewer's societies.

        The viewer is resolved from ``request.user``. The optional
        ``viewer_persona`` query param disambiguates among the
        requester's own personas; a pk that doesn't belong to the
        requester 403s.
        """
        target = self.get_object()
        try:
            viewer_persona = _resolve_request_viewer_persona(request)
        except _BadViewerPersona as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        except _ForbiddenViewerPersona:
            return Response(
                {"detail": "viewer_persona must belong to the requesting account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = build_renown_card_payload(target, viewer_persona=viewer_persona)
        serializer = RenownCardSerializer(payload)
        return Response(serializer.data)

    def get_permissions(self) -> list[BasePermission]:
        # #744: renown / renown-card are read-only views that any
        # authenticated user can read on any sheet. CanCreatePersonaInScene
        # gates write/create paths only.
        if self.action in {"renown", "renown_card"}:
            return [permissions.IsAuthenticated()]
        return [permission() for permission in self.permission_classes]


class _BadViewerPersona(Exception):
    """The viewer_persona query param could not be parsed or resolved.

    Carries an explicit ``user_message`` for the API response so we
    never round-trip ``str(exc)`` (would leak the formatted call site
    + traceback context per CodeQL's "Information exposure through an
    exception" rule).
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class _ForbiddenViewerPersona(Exception):
    """The viewer_persona pk exists but doesn't belong to the requesting account."""


def _resolve_request_viewer_persona(request: Request) -> Persona | None:
    """Resolve the viewer's persona from request.user (+ optional pk hint).

    Behaviour:
    * Unauthenticated → ``None`` (anonymous view).
    * Explicit ``viewer_persona`` query pk → must resolve to a Persona
      whose character is currently tenured by the requesting account,
      else 400/403.
    * No query pk → first such persona alphabetically, else ``None``.
    """
    if not request.user.is_authenticated:
        return None
    viewer_pk_raw = request.query_params.get("viewer_persona")  # noqa: USE_FILTERSET
    own_persona_qs = Persona.objects.filter(
        character_sheet__roster_entry__tenures__player_data__account=request.user,
        character_sheet__roster_entry__tenures__end_date__isnull=True,
    ).distinct()
    if viewer_pk_raw is not None:
        try:
            viewer_pk = int(viewer_pk_raw)
        except ValueError as exc:
            msg = "viewer_persona must be an integer."
            raise _BadViewerPersona(msg) from exc
        if not Persona.objects.filter(pk=viewer_pk).exists():
            msg = f"viewer_persona {viewer_pk} does not exist."
            raise _BadViewerPersona(msg)
        try:
            return own_persona_qs.get(pk=viewer_pk)
        except Persona.DoesNotExist as exc:
            raise _ForbiddenViewerPersona from exc
    return own_persona_qs.order_by("name").first()


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
