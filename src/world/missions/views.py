"""DRF viewsets for the missions authoring API (Phase D).

D1 ships ``MissionTemplateViewSet`` — staff-only browse + detail. D2
adds editor CRUD for nodes / options / routes / candidates / rewards.
D3 adds the giver library. D4 adds the visibility flip + copy +
staff-power actions. D5 adds the predicate-tree API.

Every viewset in this module uses the project conventions:
- ``IsAuthenticated + IsAdminUser`` permission stack (401 vs 403 split).
  ``IsAdminUser`` is DRF's built-in check on ``request.user.is_staff``;
  reusing it instead of a per-app reimplementation (e.g. the older
  ``IsStaffPermission`` in character_creation) keeps the staff-permission
  surface uniform across world/ apps.
- A ``FilterSet`` (never raw request.query_params).
- Explicit ``.order_by(...)`` for stable pagination.
- ``ModelViewSet`` when full CRUD applies; ``ReadOnlyModelViewSet`` for
  pure browse; ``viewsets.ViewSet`` + ``@extend_schema`` for non-CRUD
  surfaces per project_drf_spectacular_viewset_break.
"""

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.missions.filters import (
    MissionGiverFilterSet,
    MissionNodeFilterSet,
    MissionOptionFilterSet,
    MissionOptionRouteCandidateFilterSet,
    MissionOptionRouteFilterSet,
    MissionOptionRouteRewardFilterSet,
    MissionTemplateFilterSet,
)
from world.missions.models import (
    MissionCategory,
    MissionGiver,
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)
from world.missions.serializers import (
    BeatResolveRequestSerializer,
    BeatViewSerializer,
    JournalEntrySerializer,
    MissionCategorySerializer,
    MissionGiverSerializer,
    MissionInstanceSerializer,
    MissionNodeSerializer,
    MissionOptionRouteCandidateSerializer,
    MissionOptionRouteRewardSerializer,
    MissionOptionRouteSerializer,
    MissionOptionSerializer,
    MissionTemplateDetailSerializer,
    MissionTemplateSerializer,
    ResolvedBeatSerializer,
)
from world.predicates.catalog import leaf_params
from world.predicates.predicates import LEAF_RESOLVERS


class MissionStudioPagination(PageNumberPagination):
    """Shared pagination for the missions authoring API."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class MissionTemplateViewSet(viewsets.ModelViewSet):
    """Staff-only browse + edit endpoint for MissionTemplate rows.

    List: paginated, filterable (see MissionTemplateFilterSet), ordered
    by primary key for stable pagination.

    Detail (D1.3, pending): returns the §5 footprint — lifetime
    completions + currently-active MissionInstance rows + their current
    node — via a custom action overriding ``retrieve()``.

    Editor CRUD on nodes / options / routes is in dedicated viewsets
    (per "separate ViewSet for related-model CRUD" rule); this viewset
    only mutates MissionTemplate's own fields.
    """

    # `prefetch_related("categories")` is intentionally a bare string here
    # rather than `Prefetch(..., to_attr=...)`: DRF's default M2M serialization
    # reads `.categories.all()`, which uses the prefetched cache for bare-string
    # prefetches. Switching to `to_attr` would require a custom serializer field
    # to read from the alias, which is more code than the perf win warrants for
    # a simple PK-list M2M.
    queryset = (
        MissionTemplate.objects.all()
        .prefetch_related("categories")  # noqa: PREFETCH_STRING
        .order_by("pk")
    )
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionTemplateFilterSet

    def get_serializer_class(self) -> type[BaseSerializer[MissionTemplate]]:
        """Detail (retrieve) uses the augmented serializer; list+CRUD use the basic one.

        ``MissionTemplateDetailSerializer`` extends the list serializer with
        the §5 footprint (lifetime completions + active instances). All
        other actions use the lighter list serializer.
        """
        if self.action == "retrieve":
            return MissionTemplateDetailSerializer
        return MissionTemplateSerializer

    @action(detail=True, methods=("POST",))
    def copy(self, request: Request, pk: int | None = None) -> Response:
        """D4.2 — duplicate this template + its full graph.

        POST body: ``{"new_name": str}`` — optional. If absent, the
        service auto-suffixes the source name via next_available_name
        (``"Heist (copy)"``, ``"Heist (copy) 2"``, ...). All copied
        flavor fields are flagged ``needs_rewrite``.
        """
        from world.missions.services.copy import copy_template  # noqa: PLC0415

        source = self.get_object()
        new_name = request.data.get("new_name")
        if new_name is not None and not new_name.strip():
            return Response(
                {"new_name": ["May not be blank."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_template = copy_template(source, new_name=new_name)
        serializer = MissionTemplateSerializer(new_template, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("POST",))
    def assign(self, request: Request, pk: int | None = None) -> Response:
        """D4.3 — staff-power: drop this mission on a character.

        POST body: ``{"character": <ObjectDB pk>}``. Bypasses all
        availability filters (visibility / predicate / cooldown / level
        band) — operator gesture, not a normal acceptance flow. Returns
        the new MissionInstance shape.
        """
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

        template = self.get_object()
        character_id = request.data.get("character")
        if not character_id:
            return Response(
                {"detail": "character (ObjectDB pk) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            character = ObjectDB.objects.get(pk=character_id)
        except ObjectDB.DoesNotExist:
            return Response(
                {"detail": f"No character with pk={character_id}."},
                status=status.HTTP_404_NOT_FOUND,
            )
        instance = staff_assign_mission(template, character)
        serializer = MissionInstanceSerializer(instance, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# D2 editor CRUD viewsets — one per nested model, each a full ModelViewSet
# (list/retrieve/create/update/partial-update/destroy). Filtered by parent
# FK (template/node/option/route) via the per-model FilterSets. Staff-only.
# ---------------------------------------------------------------------------


class MissionNodeViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionNode rows."""

    queryset = MissionNode.objects.all().order_by("pk")
    serializer_class = MissionNodeSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionNodeFilterSet

    @action(detail=True, methods=("POST",))
    def copy(self, request: Request, pk: str | None = None) -> Response:
        """D4.2 — duplicate this single node within its template.

        POST body: ``{"new_key": str}``. Routes keep their original
        target_node FKs; the copy is "stuck" until the author re-wires.
        Useful for "duplicate this entry and tweak."
        """
        from world.missions.services.copy import copy_node  # noqa: PLC0415

        source = self.get_object()
        new_key = request.data.get("new_key")
        if not new_key:
            return Response(
                {"detail": "new_key is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_node = copy_node(source, new_key=new_key)
        serializer = MissionNodeSerializer(new_node, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("POST",), url_path="copy-subtree")
    def copy_subtree(self, request: Request, pk: str | None = None) -> Response:
        """D4.2 — duplicate this node + every downstream reachable node.

        POST body: ``{"new_key_prefix": str}``. Routes within the copied
        set are re-pointed to copies; routes targeting external nodes
        keep the original pointer + needs_rewrite flag.
        """
        from world.missions.services.copy import copy_subtree  # noqa: PLC0415

        source = self.get_object()
        new_key_prefix = request.data.get("new_key_prefix")
        if not new_key_prefix:
            return Response(
                {"detail": "new_key_prefix is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_node = copy_subtree(source, new_key_prefix=new_key_prefix)
        serializer = MissionNodeSerializer(new_node, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MissionOptionViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOption rows (authored + challenge-sourced)."""

    queryset = MissionOption.objects.all().order_by("pk")
    serializer_class = MissionOptionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionFilterSet


class MissionOptionRouteViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRoute (one row per option per outcome tier)."""

    queryset = MissionOptionRoute.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteFilterSet


class MissionOptionRouteCandidateViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRouteCandidate (random-set rolls)."""

    queryset = MissionOptionRouteCandidate.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteCandidateSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteCandidateFilterSet


class MissionOptionRouteRewardViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRouteReward rows (XOR route/candidate parent)."""

    queryset = MissionOptionRouteReward.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteRewardSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteRewardFilterSet


class MissionInstanceViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-power read + delete for MissionInstance rows.

    No create endpoint — instances are spawned by ``accept_mission``
    (player flow), ``staff_assign_mission`` (D4.3 assign action above),
    or future Beat-driven launches. The Studio's "remove a stuck instance"
    operation uses DELETE here.

    No update endpoint — instance state is the tuple of (current_node +
    snapshots + deeds) per design §7 invariant; the Studio doesn't mutate
    it directly.
    """

    queryset = MissionInstance.objects.all().order_by("pk")
    serializer_class = MissionInstanceSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination


class MissionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only browse of seeded MissionCategory rows.

    Categories are managed via fixture/admin — no authoring endpoints.
    The Mission Studio uses this to populate the category multi-select
    on the create page and the edit-categories dialog.
    """

    queryset = MissionCategory.objects.all().order_by("display_order", "name")
    serializer_class = MissionCategorySerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = []
    pagination_class = MissionStudioPagination


# ---------------------------------------------------------------------------
# D5 predicate-tree API — list the registry's available leaf types so the
# Mission Studio's predicate-tree builder can render leaf-type dropdowns.
# Read/write of the rule trees themselves is already covered by the
# JSONField on MissionTemplate.availability_rule and MissionOption.
# visibility_rule (D1/D2 serializers round-trip them as-is).
# ---------------------------------------------------------------------------


class PredicateLeafCatalogViewSet(viewsets.ViewSet):
    """D5 — the available predicate-leaf catalog for the builder palette.

    Read-only. Returns ``[{"name": str, "params": [{"name": str, "type":
    str}, ...]}]`` for every leaf in ``LEAF_RESOLVERS``. The Mission
    Studio's predicate-tree builder uses this to render leaf-type
    dropdowns + per-param input widgets typed correctly (int vs str)
    without hard-coding the registry on the frontend. Param introspection
    lives in ``world.predicates.catalog`` — shared with the server-side
    tree validator (#870) so palette and validation can't drift.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="List of available predicate leaves.")},
    )
    def list(self, request: Request) -> Response:
        catalog = [
            {"name": name, "params": leaf_params(resolver)}
            for name, resolver in sorted(LEAF_RESOLVERS.items())
        ]
        return Response(catalog)


class MissionGiverViewSet(viewsets.ModelViewSet):
    """Staff CRUD for trigger-based MissionGiver rows (#729).

    Covers the two surviving GiverKind variants (ROOM_TRIGGER,
    ENVIRONMENTAL_DETAIL); NPC-mediated giving lives on the npc-services
    offer framework (#686/#728). ``templates`` is a flat M2M draw pool —
    each template self-gates at draw time via its own ``availability_rule``
    (Option A, #729).
    """

    queryset = MissionGiver.objects.all().prefetch_related("templates").order_by("pk")  # noqa: PREFETCH_STRING
    serializer_class = MissionGiverSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverFilterSet


# ---------------------------------------------------------------------------
# #885 player journal/beat surface — the first PLAYER-scoped missions API
# (everything above is staff authoring/ops). Wires the previously
# caller-less ``journal_for`` plus the new ``services.play`` orchestration.
# ---------------------------------------------------------------------------


_MSG_NO_SUCH_MISSION = "No such mission."
_MSG_RUN_CONCLUDED = "That mission has concluded — see your journal for the epilogue."


def _journal_paginated_response() -> serializers.Serializer:
    """Inline schema for the paginated journal list (items-app pattern)."""
    return inline_serializer(
        name="PaginatedJournalEntryList",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": JournalEntrySerializer(many=True),
        },
    )


def _puppet_character(request: Request) -> "ObjectDB":
    """Return the user's currently-puppeted Character ObjectDB.

    Mirrors ``npc_services.views.InteractionViewSet._puppet_character``
    (DRF's ``request.user`` is the AccountDB; ``puppet`` is the live
    puppet or None). Surfaced as 400 — the client must assume a character
    before using the journal.
    """
    from rest_framework.exceptions import ValidationError  # noqa: PLC0415

    try:
        puppet = request.user.puppet
    except (AttributeError, Exception):  # noqa: BLE001
        puppet = None
    if puppet is None:
        msg = "No puppeted character — assume a character before using the journal."
        raise ValidationError(msg)
    return puppet


class MissionJournalViewSet(viewsets.ViewSet):
    """#885 — the player's mission journal + beat play loop.

    list: every mission the puppeted character participates in (compass +
    deeds + bookends). beat: the current node as the character sees it —
    LIVE options only (location ∧ visibility; visibility=eligibility, no
    greyed-out entries). resolve: take an option; the engine rolls and
    routes; the actor gets clear STORY prose, the room gets a
    source-ambiguous ambient stir.

    Participant gating: a non-participant probing instance ids gets 404
    (never 403 — existence must not leak).
    """

    permission_classes = [IsAuthenticated]

    def _instance_for(self, request: Request, pk: str | None) -> "tuple[MissionInstance, ObjectDB]":
        from rest_framework.exceptions import NotFound  # noqa: PLC0415

        from world.missions.services.play import (  # noqa: PLC0415
            NotParticipantError,
            participant_for,
        )

        character = _puppet_character(request)
        instance = MissionInstance.objects.filter(pk=pk).first()
        if instance is None:
            raise NotFound(_MSG_NO_SUCH_MISSION)
        try:
            participant_for(instance, character)
        except NotParticipantError as exc:
            raise NotFound(exc.user_message) from exc
        return instance, character

    @extend_schema(responses=_journal_paginated_response())
    def list(self, request: Request) -> Response:
        from world.missions.services.journal import journal_for  # noqa: PLC0415

        character = _puppet_character(request)
        entries = journal_for(character)
        paginator = MissionStudioPagination()
        # DRF pagination accepts any sized iterable at runtime; the stub
        # wants a QuerySet — cast keeps ty happy without a real conversion.
        page = paginator.paginate_queryset(cast("Any", entries), request)
        serializer = JournalEntrySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        responses={
            200: BeatViewSerializer,
            404: OpenApiResponse(description="Not a participant / run concluded."),
        },
    )
    @action(detail=True, methods=("GET",))
    def beat(self, request: Request, pk: str | None = None) -> Response:
        from rest_framework.exceptions import NotFound  # noqa: PLC0415

        from world.missions.services.play import beat_for  # noqa: PLC0415

        instance, character = self._instance_for(request, pk)
        beat = beat_for(instance, character)
        if beat is None:
            raise NotFound(_MSG_RUN_CONCLUDED)
        return Response(BeatViewSerializer(beat).data)

    @extend_schema(
        request=BeatResolveRequestSerializer,
        responses={
            200: ResolvedBeatSerializer,
            400: OpenApiResponse(description="Option not live here / run not active."),
            404: OpenApiResponse(description="Not a participant / no such mission."),
        },
    )
    @action(detail=True, methods=("POST",))
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        from rest_framework.exceptions import ValidationError  # noqa: PLC0415

        from world.missions.services.play import (  # noqa: PLC0415
            BeatActionError,
            resolve_beat_option,
        )

        body = BeatResolveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        instance, character = self._instance_for(request, pk)
        try:
            result = resolve_beat_option(
                instance,
                character,
                option_id=body.validated_data["option_id"],
                approach_id=body.validated_data.get("approach_id"),
            )
        except BeatActionError as exc:
            # Typed exception with a user-safe message — never str() of
            # an internal error (CodeQL exception-exposure rule).
            raise ValidationError(exc.user_message) from exc
        return Response(ResolvedBeatSerializer(result).data)
