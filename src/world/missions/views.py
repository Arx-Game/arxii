"""DRF viewsets for the missions authoring API (Phase D).

D1 ships ``MissionTemplateViewSet`` — staff-only browse + detail. D2
adds editor CRUD for nodes / options / routes / candidates / rewards.
D3 adds the giver library. D4 adds access-tier flip + copy + staff-power
actions. D5 adds the predicate-tree API.

Every viewset in this module uses the project conventions:
- ``IsAuthenticated + IsStaff`` permission stack (401 vs 403 split).
- A ``FilterSet`` (never raw request.query_params).
- Explicit ``.order_by(...)`` for stable pagination.
- ``ModelViewSet`` when full CRUD applies; ``ReadOnlyModelViewSet`` for
  pure browse; ``viewsets.ViewSet`` + ``@extend_schema`` for non-CRUD
  surfaces per project_drf_spectacular_viewset_break.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
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
    MissionGiver,
    MissionGiverOffering,
    MissionGiverStanding,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)
from world.missions.permissions import IsStaff
from world.missions.serializers import (
    MissionGiverOfferingSerializer,
    MissionGiverSerializer,
    MissionGiverStandingSerializer,
    MissionNodeSerializer,
    MissionOptionRouteCandidateSerializer,
    MissionOptionRouteRewardSerializer,
    MissionOptionRouteSerializer,
    MissionOptionSerializer,
    MissionTemplateDetailSerializer,
    MissionTemplateSerializer,
)


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
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionTemplateFilterSet
    lookup_field = "slug"

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
    def copy(self, request: Request, slug: str | None = None) -> Response:
        """D4.2 — duplicate this template + its full graph.

        POST body: ``{"new_slug": str, "new_name": str}``. Lands the copy
        with ``access_tier=STAFF_ONLY`` so the author can fix flavor before
        publishing. All copied flavor fields are flagged needs_rewrite.
        """
        from world.missions.services.copy import copy_template  # noqa: PLC0415

        source = self.get_object()
        new_slug = request.data.get("new_slug")
        new_name = request.data.get("new_name")
        if not new_slug or not new_name:
            return Response(
                {"detail": "new_slug and new_name are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_template = copy_template(source, new_slug=new_slug, new_name=new_name)
        serializer = MissionTemplateSerializer(new_template, context={"request": request})
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
    permission_classes = [IsAuthenticated, IsStaff]
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
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionFilterSet


class MissionOptionRouteViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRoute (one row per option per outcome tier)."""

    queryset = MissionOptionRoute.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteFilterSet


class MissionOptionRouteCandidateViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRouteCandidate (random-set rolls)."""

    queryset = MissionOptionRouteCandidate.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteCandidateSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteCandidateFilterSet


class MissionOptionRouteRewardViewSet(viewsets.ModelViewSet):
    """Editor CRUD for MissionOptionRouteReward rows (XOR route/candidate parent)."""

    queryset = MissionOptionRouteReward.objects.all().order_by("pk")
    serializer_class = MissionOptionRouteRewardSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOptionRouteRewardFilterSet


# ---------------------------------------------------------------------------
# D3 giver-library viewsets — staff CRUD for MissionGiver + its links to
# templates (MissionGiverOffering) and per-character standing rows
# (MissionGiverStanding).
# ---------------------------------------------------------------------------


class MissionGiverViewSet(viewsets.ModelViewSet):
    """Staff CRUD for MissionGiver. Slug-keyed; clean() validates target typeclass."""

    queryset = MissionGiver.objects.all().order_by("pk")
    serializer_class = MissionGiverSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverFilterSet
    lookup_field = "slug"


class MissionGiverOfferingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for the giver<->template through-model."""

    queryset = MissionGiverOffering.objects.all().order_by("pk")
    serializer_class = MissionGiverOfferingSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverOfferingFilterSet


class MissionGiverStandingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for per-(giver, character) standing rows.

    Normally written by ``services.run.accept_mission`` (cooldown side)
    and future flirt/seduce checks (affection side). CRUD here is for
    staff overrides — clear a cooldown, bump or penalize affection.
    """

    queryset = MissionGiverStanding.objects.all().order_by("pk")
    serializer_class = MissionGiverStandingSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class = MissionStudioPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionGiverStandingFilterSet
