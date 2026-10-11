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
from rest_framework.views import APIView

from world.realms.models import Realm
from world.roster.models import Family, FamilyKind, Kinsperson, UnionKind
from world.roster.views.family_views import _viewer_entry
from world.societies.houses.almanach_pages import (
    family_document,
    front_rolls,
    person_document,
    rung_document,
    search,
)
from world.societies.houses.almanach_reads import (
    charter_for_realm,
    document_for_house,
    ladder_for_realm,
)
from world.societies.houses.almanach_serializers import (
    AlmanachFamilyKindSerializer,
    AlmanachFamilySummarySerializer,
    AlmanachHoldingKindSerializer,
    AlmanachHouseSummarySerializer,
    AlmanachPersonSummarySerializer,
    AlmanachRealmSerializer,
    AlmanachTemplateSerializer,
    AlmanachTitleSummarySerializer,
    AlmanachUnionKindSerializer,
    FamilyDocumentSerializer,
    FrontRollsSerializer,
    HouseDocumentSerializer,
    LadderPayloadSerializer,
    LandShapeSerializer,
    PersonDocumentSerializer,
    RealmCharterSerializer,
    RungDocumentSerializer,
    SearchHitSerializer,
)
from world.societies.houses.models import HoldingKind, HouseTemplate, LandShape, Title
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


# ---------------------------------------------------------------------------
# #4239: every family, every person. Staff-only reads for the person, title
# and family pages, the front page's rolls, and search.
# ---------------------------------------------------------------------------

_STAFF = [permissions.IsAuthenticated, permissions.IsAdminUser]


class AlmanachPersonViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve people, plus each person's page (``/document/``)."""

    queryset = Kinsperson.objects.all().order_by("name")
    serializer_class = AlmanachPersonSummarySerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["family", "is_appable", "definition_tier"]

    @extend_schema(responses=PersonDocumentSerializer)
    @action(detail=True, methods=["get"], url_path="document")
    def document(self, request, pk=None):
        """GET /api/almanach/people/{id}/document/"""
        return Response(PersonDocumentSerializer(person_document(self.get_object())).data)


class AlmanachTitleViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve titles, plus each rung's page (``/document/``)."""

    queryset = Title.objects.all().order_by("realm__name", "name")
    serializer_class = AlmanachTitleSummarySerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["realm", "house", "tier", "is_claimable"]

    @extend_schema(responses=RungDocumentSerializer)
    @action(detail=True, methods=["get"], url_path="document")
    def document(self, request, pk=None):
        """GET /api/almanach/titles/{id}/document/"""
        return Response(RungDocumentSerializer(rung_document(self.get_object())).data)


class AlmanachFamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve families, plus each family's page (``/document/``): the
    family half of the house document, which works with no organization."""

    queryset = Family.objects.all().select_related("kind").order_by("name")
    serializer_class = AlmanachFamilySummarySerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["kind", "origin_realm", "is_playable"]

    @extend_schema(responses=FamilyDocumentSerializer)
    @action(detail=True, methods=["get"], url_path="document")
    def document(self, request, pk=None):
        """GET /api/almanach/families/{id}/document/"""
        viewer = _viewer_entry(request)
        payload = family_document(self.get_object(), viewer=viewer, staff=request.user.is_staff)
        return Response(FamilyDocumentSerializer(payload).data)


class AlmanachFrontView(APIView):
    """GET /api/almanach/front/?q=: the three rolls, narrowed by ``q``."""

    permission_classes = _STAFF

    @extend_schema(
        parameters=[OpenApiParameter(name="q", type=str, required=False)],
        responses=FrontRollsSerializer,
    )
    def get(self, request):
        # A free-text narrowing of a computed payload, not a queryset filter;
        # there is no queryset for a FilterSet to attach to.
        q = request.query_params.get("q", "")  # noqa: USE_FILTERSET
        return Response(FrontRollsSerializer(front_rolls(q=q)).data)


class AlmanachSearchView(APIView):
    """GET /api/almanach/search/?q=: people, families, organizations, titles."""

    permission_classes = _STAFF

    @extend_schema(
        parameters=[OpenApiParameter(name="q", type=str, required=True)],
        responses=SearchHitSerializer(many=True),
    )
    def get(self, request):
        # Four tables, one capped name search; a FilterSet binds to one queryset.
        q = request.query_params.get("q", "")  # noqa: USE_FILTERSET
        return Response(SearchHitSerializer(search(q), many=True).data)


class AlmanachFamilyKindViewSet(viewsets.ReadOnlyModelViewSet):
    """The family types Create Family offers."""

    queryset = FamilyKind.objects.filter(is_active=True).order_by("sort_order", "name")
    serializer_class = AlmanachFamilyKindSerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["styles_as_house"]


class AlmanachTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """Family Templates, filtered by realm and kind for the Create Family form."""

    queryset = HouseTemplate.objects.all().order_by("realm__name", "kind__name", "name")
    serializer_class = AlmanachTemplateSerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["realm", "kind"]


class AlmanachUnionKindViewSet(viewsets.ReadOnlyModelViewSet):
    """Union kinds, filtered by realm for Add spouse."""

    queryset = UnionKind.objects.all().order_by("realm__name", "name")
    serializer_class = AlmanachUnionKindSerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["realm"]


class AlmanachHoldingKindViewSet(viewsets.ReadOnlyModelViewSet):
    """The holding catalog, for Add holding."""

    queryset = HoldingKind.objects.all().order_by("name")
    serializer_class = AlmanachHoldingKindSerializer
    permission_classes = _STAFF
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["site_kind"]
