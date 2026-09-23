"""DRF viewsets for the Almanach de Catenys API (#3983): the house-builder
reads — the realm ladder, the realm charter, a house's document, and the
land-shape catalog. The realm list/ladder/charter and the land-shape catalog
are open to any authenticated account (Task 3, Plan B) so a founder can read
them mid-draft; the ``?for=staff`` ladder cut and the houses viewset (house
list + document) stay ``IsAdminUser``.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from world.realms.models import Realm
from world.roster.views.family_views import _viewer_entry
from world.societies.houses.almanach_reads import (
    charter_for_realm,
    document_for_house,
    ladder_for_realm,
)
from world.societies.houses.almanach_serializers import (
    AlmanachHouseSummarySerializer,
    AlmanachRealmSerializer,
    HouseDocumentSerializer,
    LadderPayloadSerializer,
    LandShapeSerializer,
    RealmCharterSerializer,
)
from world.societies.houses.models import LandShape
from world.societies.models import Organization
from world.societies.views import SocietiesPagination

_LADDER_CUT_STAFF = "staff"
_LADDER_CUT_FOUNDER = "founder"


class AlmanachHouseFilter(django_filters.FilterSet):
    """``?realm=<id>``: an Organization has no realm column of its own, so
    this filters through the family's canonical ``origin_realm``
    (``roster/models/families.py``)."""

    realm = django_filters.NumberFilter(field_name="family__origin_realm_id")

    class Meta:
        model = Organization
        fields = ["realm"]


class AlmanachRealmViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve realms for the Almanach's realm picker, plus each
    realm's feudal ladder (``/ladder/``)."""

    queryset = Realm.objects.all().order_by("name")
    serializer_class = AlmanachRealmSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name"]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="for",
                type=str,
                required=False,
                enum=[_LADDER_CUT_STAFF, _LADDER_CUT_FOUNDER],
                description=(
                    "Which ladder cut to read: 'staff' (default) shows every rung and "
                    "needs staff; 'founder' hides rungs sitting under an unpublished "
                    "house and is open to any authenticated account."
                ),
            )
        ],
        responses=LadderPayloadSerializer,
    )
    @action(detail=True, methods=["get"], url_path="ladder")
    def ladder(self, request, pk=None):
        """GET /api/almanach/realms/{id}/ladder/?for=staff|founder"""
        realm = self.get_object()
        # A ladder-cut selector, not a queryset filter — a FilterSet has no
        # queryset to attach to here (the action returns a computed payload,
        # not a filtered list).
        cut = request.query_params.get("for", _LADDER_CUT_STAFF)  # noqa: USE_FILTERSET
        if cut != _LADDER_CUT_FOUNDER and not request.user.is_staff:
            msg = "The full ladder is staff-only."
            raise PermissionDenied(msg)
        payload = ladder_for_realm(realm, for_founder=cut == _LADDER_CUT_FOUNDER)
        return Response(LadderPayloadSerializer(payload).data)

    @extend_schema(responses=RealmCharterSerializer)
    @action(detail=True, methods=["get"], url_path="charter")
    def charter(self, request, pk=None):
        """GET /api/almanach/realms/{id}/charter/: the founder ladder's defaults."""
        realm = self.get_object()
        payload = charter_for_realm(realm)
        return Response(RealmCharterSerializer(payload).data)


class AlmanachHouseViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve houses (orgs with a family), plus each house's full
    Almanach document (``/document/``)."""

    queryset = Organization.objects.filter(family__isnull=False).order_by("name")
    serializer_class = AlmanachHouseSummarySerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = AlmanachHouseFilter

    @extend_schema(responses=HouseDocumentSerializer)
    @action(detail=True, methods=["get"], url_path="document")
    def document(self, request, pk=None):
        """GET /api/almanach/houses/{id}/document/"""
        house = self.get_object()
        # Reuses roster's own kinship-viewer resolution (staff -> OMNISCIENT,
        # else the account's RosterEntry, or None mid-CG) rather than a
        # second copy — the almanach document folds in a family_tree_for()
        # read, and that call's visibility contract is exactly this one
        # (world/roster/services/kinship.py's _viewer_knows isinstance-checks
        # for RosterEntry/OMNISCIENT, never a CharacterSheet).
        viewer = _viewer_entry(request)
        payload = document_for_house(house, viewer=viewer, staff=request.user.is_staff)
        return Response(HouseDocumentSerializer(payload).data)


class LandShapeViewSet(viewsets.ReadOnlyModelViewSet):
    """The authored land-shape catalog (coast, reefs, hills, volcanic, ...)."""

    queryset = LandShape.objects.all()
    serializer_class = LandShapeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name"]
