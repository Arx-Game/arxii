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
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from world.missions.filters import (
    MissionNodeFilterSet,
    MissionOptionFilterSet,
    MissionOptionRouteCandidateFilterSet,
    MissionOptionRouteFilterSet,
    MissionOptionRouteRewardFilterSet,
    MissionTemplateFilterSet,
)
from world.missions.models import (
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)
from world.missions.permissions import IsStaff
from world.missions.serializers import (
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
