"""DRF viewsets for the missions authoring API (Phase D).

D1 ships ``MissionTemplateViewSet`` — staff-only browse + detail. D2
adds editor CRUD for nodes / options / routes / candidates / rewards.
D3 adds the giver library. D4 adds access-tier flip + copy + staff-power
actions. D5 adds the predicate-tree API.

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

import inspect

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.missions.filters import (
    MissionGiverFilterSet,
    MissionGiverOfferingFilterSet,
    MissionGiverStandingFilterSet,
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
    MissionGiverOffering,
    MissionGiverStanding,
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)
from world.missions.predicates import LEAF_RESOLVERS
from world.missions.serializers import (
    MissionCategorySerializer,
    MissionGiverOfferingSerializer,
    MissionGiverSerializer,
    MissionGiverStandingSerializer,
    MissionInstanceSerializer,
    MissionNodeSerializer,
    MissionOptionRouteCandidateSerializer,
    MissionOptionRouteRewardSerializer,
    MissionOptionRouteSerializer,
    MissionOptionSerializer,
    MissionTemplateDetailSerializer,
    MissionTemplateSerializer,
)
from world.missions.types import LeafResolver


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

    queryset = MissionTemplate.objects.all().order_by("pk")
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
        availability filters (predicate / cooldown / level band / access
        tier) — operator gesture, not a normal acceptance flow. Returns
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


# ---------------------------------------------------------------------------
# D3 giver-library viewsets — staff CRUD for MissionGiver + its links to
# templates (MissionGiverOffering) and per-character standing rows
# (MissionGiverStanding).
# ---------------------------------------------------------------------------


class MissionGiverViewSet(viewsets.ModelViewSet):
    """Staff CRUD for MissionGiver. clean() validates target typeclass."""

    queryset = MissionGiver.objects.all().order_by("pk")
    serializer_class = MissionGiverSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverFilterSet


class MissionGiverOfferingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for the giver<->template through-model."""

    queryset = MissionGiverOffering.objects.all().order_by("pk")
    serializer_class = MissionGiverOfferingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverOfferingFilterSet


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


class MissionGiverStandingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for per-(giver, character) standing rows.

    Normally written by ``services.run.accept_mission`` (cooldown side)
    and future flirt/seduce checks (affection side). CRUD here is for
    staff overrides — clear a cooldown, bump or penalize affection.
    """

    queryset = MissionGiverStanding.objects.all().order_by("pk")
    serializer_class = MissionGiverStandingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverStandingFilterSet


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


_TYPE_TAGS: dict[type, str] = {int: "int", bool: "bool", str: "str", float: "float"}


def _annotation_tag(annotation: object) -> str:
    """Map a resolver param annotation to a string tag the FE can switch on.

    Used by the predicate-leaf catalog endpoint so the Studio's builder
    can coerce ``<Input>`` strings into the right Python type before save
    — without this, int-typed leaves (e.g. ``min_character_level``) blow
    up at evaluate time with ``TypeError: '>=' not supported between
    instances of 'int' and 'str'``.

    Unknown / unannotated params fall back to ``"str"`` (the safe default
    — most resolvers either accept a slug or ``int(...)``-coerce on read).
    """
    return _TYPE_TAGS.get(annotation, "str") if isinstance(annotation, type) else "str"


def _leaf_params(resolver: LeafResolver) -> list[dict[str, str]]:
    """Return the leaf's authored param names + type tags (everything after ctx).

    The resolver module uses ``from __future__ import annotations``, so
    ``Parameter.annotation`` is a string rather than the type object.
    Re-resolve via ``typing.get_type_hints`` so the tag mapping works.
    """
    import typing  # noqa: PLC0415

    sig = inspect.signature(resolver)
    try:
        hints = typing.get_type_hints(resolver)
    except (NameError, AttributeError, TypeError):
        # If a resolver's annotations reference an as-yet-unresolvable
        # forward reference (NameError) or a non-evaluable annotation
        # (TypeError / AttributeError on inner typing surfaces), fall
        # back to the raw (string) annotation — which falls through to
        # "str" via the isinstance check in _annotation_tag.
        hints = {}
    return [
        {"name": name, "type": _annotation_tag(hints.get(name, param.annotation))}
        for name, param in list(sig.parameters.items())[1:]
        if param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]


class PredicateLeafCatalogViewSet(viewsets.ViewSet):
    """D5 — the available predicate-leaf catalog for the builder palette.

    Read-only. Returns ``[{"name": str, "params": [{"name": str, "type":
    str}, ...]}]`` for every leaf in ``LEAF_RESOLVERS``. The Mission
    Studio's predicate-tree builder uses this to render leaf-type
    dropdowns + per-param input widgets typed correctly (int vs str)
    without hard-coding the registry on the frontend.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="List of available predicate leaves.")},
    )
    def list(self, request: Request) -> Response:
        catalog = [
            {"name": name, "params": _leaf_params(resolver)}
            for name, resolver in sorted(LEAF_RESOLVERS.items())
        ]
        return Response(catalog)
