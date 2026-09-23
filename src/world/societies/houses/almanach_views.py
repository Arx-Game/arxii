"""DRF viewsets for the Almanach de Catenys API (#3983): the staff-only
house-builder reads — the realm ladder, a house's document, and the
land-shape catalog. Every route here is gated ``IsAdminUser``; the
``?for=founder`` ladder cut is exposed now but stays staff-only until Plan B
opens it to house founders mid-draft.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from world.realms.models import Realm
from world.societies.houses.almanach_reads import document_for_house, ladder_for_realm
from world.societies.houses.almanach_serializers import (
    AlmanachHouseSummarySerializer,
    AlmanachRealmSerializer,
    HouseDocumentSerializer,
    LadderPayloadSerializer,
    LandShapeSerializer,
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


def _viewer_for_request(request) -> object:
    """The account's active character sheet, or None (#3983 Task 5 spec).

    ``document_for_house`` only actually reads this for a non-staff caller
    (``staff=True`` reads the family tree with the omniscient viewer
    unconditionally) — every route in this module is ``IsAdminUser``-gated,
    so ``staff`` is always True today and this value is inert until Plan B
    opens a document read to a non-staff founder.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return entry.character_sheet


class AlmanachRealmViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve realms for the Almanach's realm picker, plus each
    realm's feudal ladder (``/ladder/``)."""

    queryset = Realm.objects.all().order_by("name")
    serializer_class = AlmanachRealmSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
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
                    "Which ladder cut to read: 'staff' (default) shows every rung; "
                    "'founder' hides rungs sitting under an unpublished house. Both "
                    "are staff-gated in this plan."
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
        payload = ladder_for_realm(realm, for_founder=cut == _LADDER_CUT_FOUNDER)
        return Response(LadderPayloadSerializer(payload).data)


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
        viewer = _viewer_for_request(request)
        payload = document_for_house(house, viewer=viewer, staff=request.user.is_staff)
        return Response(HouseDocumentSerializer(payload).data)


class LandShapeViewSet(viewsets.ReadOnlyModelViewSet):
    """The authored land-shape catalog (coast, reefs, hills, volcanic, ...)."""

    queryset = LandShape.objects.all()
    serializer_class = LandShapeSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["name"]
