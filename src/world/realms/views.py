"""Realm page reads (#3725, ADR-0285).

Anonymous-readable by construction: a realm page is a pitch and a set of windows onto
rows other apps already keep. ``retrieve`` is keyed by the realm's slug. The two
actions serve the hub sections that need their own shape: the shop-window list of a
realm's organizations (covert kinds only to their members) and the realm's two boards
(names and band labels, never a number).
"""

from __future__ import annotations

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from world.realms.models import Realm
from world.realms.serializers import RealmDetailSerializer, RealmListSerializer
from world.realms.services import realm_by_slug
from world.societies.models import Organization
from world.societies.permissions import active_persona_q
from world.societies.ranking_services import get_realm_legend_top_n, get_realm_renown_top_n
from world.societies.ranking_views import RankingRowSerializer
from world.societies.serializers import OrganizationShopWindowSerializer

_MSG_NO_REALM = "No realm by that name."
BOARD_SIZE = 10


class RealmBoardsSerializer(serializers.Serializer):
    """The realm's two boards. Rows carry a name and a phrase; no numeric field exists."""

    renown = RankingRowSerializer(many=True)
    legend = RankingRowSerializer(many=True)


class RealmViewSet(viewsets.ReadOnlyModelViewSet):
    """List the realms (the hub) and retrieve one by slug (the page)."""

    # A handful of rows; the sections read through the ordered relation per realm
    # (six small queries on the hub, one on the page), no prefetch to keep in step.
    queryset = Realm.objects.all().order_by("name")
    serializer_class = RealmListSerializer
    permission_classes = [AllowAny]
    pagination_class = None  # a handful of rows; the hub is the whole list (ADR-0138)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["theme"]
    lookup_field = "slug"
    lookup_value_regex = r"[-a-z0-9]+"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RealmDetailSerializer
        return RealmListSerializer

    def get_object(self) -> Realm:
        """Resolve the slug over the realm rows (the slug is derived, not stored)."""
        realm = realm_by_slug(self.kwargs[self.lookup_field])
        if realm is None:
            raise NotFound(_MSG_NO_REALM)
        return realm

    @extend_schema(responses={200: OrganizationShopWindowSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def organizations(self, request: Request, slug: str | None = None) -> Response:
        """The realm's houses and organizations as a gate would show them.

        Covert kinds (#2820) are excluded unless the viewer's active persona holds a
        live membership in that row; an anonymous viewer gets the plain exclusion.
        Covenants are not organizations here, as on the members' list.
        """
        realm = self.get_object()
        queryset = Organization.objects.filter(society__realm=realm, covenant__isnull=True)
        visible = Q(org_type__is_covert=False) | Q(org_type__isnull=True)
        if request.user.is_authenticated:
            visible |= Q(
                active_persona_q(request.user, path="memberships__persona"),
                memberships__left_at__isnull=True,
                memberships__exiled_at__isnull=True,
            )
        queryset = (
            queryset.filter(visible)
            .select_related("org_type", "society")
            .order_by("org_type__name", "name")
            .distinct()
        )
        return Response(OrganizationShopWindowSerializer(queryset, many=True).data)

    @extend_schema(responses={200: RealmBoardsSerializer})
    @action(detail=True, methods=["get"])
    def notables(self, request: Request, slug: str | None = None) -> Response:
        """The names spoken in the realm: top ten by renown and by legend (#676's addition)."""
        realm = self.get_object()
        payload = {
            "renown": get_realm_renown_top_n(realm, n=BOARD_SIZE),
            "legend": get_realm_legend_top_n(realm, n=BOARD_SIZE),
        }
        return Response(RealmBoardsSerializer(payload).data)
