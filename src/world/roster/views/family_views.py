"""Kinship API views (#2062, #3003).

Read surfaces only: families, the viewer-aware tree, the CG slot browser,
the character-scoped kin tree (``CharacterKinTreeView``), and the pairwise
relationship label (``KinRelationshipView``). Graph WRITES go through the
kinship services from CG finalization and staff admin — never generic REST
mutation (the truth/record layer and canon gating make open CRUD wrong here).
"""

from http import HTTPMethod
from typing import cast

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.roster.filters import FamilyFilterSet
from world.roster.models import Family, Kinsperson
from world.roster.serializers import (
    FamilySerializer,
    FamilyTreeSerializer,
    KinRelationshipQuerySerializer,
    KinRelationshipSerializer,
    KinSlotPoolSerializer,
    KinSlotSerializer,
)
from world.roster.services.kinship import (
    OMNISCIENT,
    derive_relationship,
    family_tree_for,
    kin_tree_for_sheet,
    open_slots_for,
)


def _viewer_entry(request: Request) -> object:
    """Resolve the visibility context: staff → OMNISCIENT; character →
    their RosterEntry; no character yet (mid-CG) → None (public record only)."""
    if request.user.is_staff:
        return OMNISCIENT
    from world.roster.models import RosterEntry  # noqa: PLC0415

    return RosterEntry.objects.for_account(cast(AccountDB, request.user)).first()


def _inherited_by_family(families: list[Family]) -> dict[int, dict]:
    """One fixed batch of flat queries for every family's inherited house facts.

    Mirrors ``character_creation.views._claimable_kind_ids_by_template`` -
    bounded to four queries regardless of how many families are being
    listed, grouped by family id in Python, and passed through serializer
    context instead of a per-row ``house_for_family``/``.aspects.all()`` call
    (``FamilySerializer.get_inherited``). Never ``Prefetch(to_attr=...)`` or a
    bare ``prefetch_related`` here - both are unreliable across requests on
    these SharedMemoryModel instances (see the roster/CLAUDE.md idmapper notes).
    """
    from world.societies.houses.models import (  # noqa: PLC0415
        FealtyEdge,
        OrganizationAspect,
        OrganizationFeature,
    )
    from world.societies.models import Organization  # noqa: PLC0415

    grouping: dict[int, dict] = {}
    if not families:
        return grouping
    family_ids = [f.pk for f in families]
    # Lowest pk per family mirrors ``family.organizations.first()``'s
    # (unordered-by-default) result closely enough for a house lookup - a
    # family has at most one org in practice.
    org_by_family: dict[int, int] = {}
    for org_id, family_id in (
        Organization.objects.filter(family_id__in=family_ids)
        .order_by("family_id", "pk")
        .values_list("pk", "family_id")
    ):
        org_by_family.setdefault(family_id, org_id)
    if not org_by_family:
        return grouping
    org_ids = list(org_by_family.values())
    family_id_by_org_id = {org_id: family_id for family_id, org_id in org_by_family.items()}

    aspects_by_org: dict[int, list[dict]] = {}
    for aspect in OrganizationAspect.objects.filter(organization_id__in=org_ids).select_related(
        "definition", "option"
    ):
        aspects_by_org.setdefault(aspect.organization_id, []).append(
            {
                "definition": aspect.definition.name,
                "option": aspect.option.name,
                "description": aspect.option.description,
            }
        )

    features_by_org: dict[int, list[dict]] = {}
    for stamped in OrganizationFeature.objects.filter(organization_id__in=org_ids).select_related(
        "feature"
    ):
        features_by_org.setdefault(stamped.organization_id, []).append(
            {
                "name": stamped.feature.name,
                "slug": stamped.feature.slug,
                "description": stamped.feature.description,
            }
        )

    liege_name_by_org: dict[int, str] = dict(
        FealtyEdge.objects.filter(vassal_id__in=org_ids).values_list("vassal_id", "liege__name")
    )

    for org_id, family_id in family_id_by_org_id.items():
        grouping[family_id] = {
            "aspects": aspects_by_org.get(org_id, []),
            "features": features_by_org.get(org_id, []),
            "liege_name": liege_name_by_org.get(org_id, ""),
        }
    return grouping


class FamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """Families list/detail + the viewer-aware tree and CG slot browser."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = (
        Family.objects.filter(is_playable=True)
        .select_related("kind")
        .order_by("kind__sort_order", "kind__name", "name")
    )
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FamilyFilterSet

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        # Serialize with one batched inherited grouping, not one per row. Mirrors
        # CGOriginTemplateViewSet.list() (this ViewSet also opts out of pagination,
        # so there is no page branch to preserve).
        families = list(self.filter_queryset(self.get_queryset()))
        context = {
            **self.get_serializer_context(),
            "inherited_by_family": _inherited_by_family(families),
        }
        serializer = self.get_serializer_class()(families, many=True, context=context)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET])
    def tree(self, request: Request, pk: int | None = None) -> Response:
        """The family's kinship graph, filtered to what the viewer may see."""
        family = self.get_object()
        payload = family_tree_for(family, _viewer_entry(request))
        serializer = FamilyTreeSerializer(
            {
                "family": payload.family,
                "nodes": payload.nodes,
                "parentage": payload.parentage,
                "unions": payload.unions,
            },
            context={"request": request},
        )
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET])
    def slots(self, request: Request, pk: int | None = None) -> Response:
        """Open appable positions + pools for this family (CG slot browser)."""
        family = self.get_object()
        nodes, pools = open_slots_for(family)
        return Response(
            {
                "slots": KinSlotSerializer(nodes, many=True).data,
                "pools": KinSlotPoolSerializer(pools, many=True).data,
            }
        )


class CharacterKinTreeView(APIView):
    """Viewer-aware kin tree centred on a single character (#3003).

    Family-bound characters get their family's tree; familyless subjects
    (Misbegotten, tarot-named) get the ego-centric payload from
    ``kin_tree_for_sheet`` — same node/edge/union shapes either way.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=FamilyTreeSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            raise NotFound from None
        payload = kin_tree_for_sheet(sheet, _viewer_entry(request))
        serializer = FamilyTreeSerializer(
            {
                "family": payload.family,
                "nodes": payload.nodes,
                "parentage": payload.parentage,
                "unions": payload.unions,
            },
            context={"request": request},
        )
        return Response(serializer.data)


class KinRelationshipView(APIView):
    """Viewer-aware relationship label between two characters (#3003).

    ``a``/``b`` are character ids (``CharacterSheet`` pks); the label is
    derived fresh from the kinship graph on every call — nothing like
    "cousin" is ever stored. No visibility logic lives here: ``viewer`` is
    threaded straight into ``derive_relationship``, which gates on
    ``fact_visible`` the same way the tree endpoint does.

    Two distinct "nothing there" cases, kept apart the same way
    ``kin_tree_for_sheet`` keeps them apart: a ``CharacterSheet`` pk that
    doesn't exist is a genuine 404, while a real ``CharacterSheet`` with no
    ``Kinsperson`` node yet (no CG kinship record) is a valid empty state —
    200 with ``{"label": null}``, not a 404.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("a", int, required=True, description="First character's id."),
            OpenApiParameter("b", int, required=True, description="Second character's id."),
        ],
        responses=KinRelationshipSerializer,
    )
    def get(self, request: Request) -> Response:
        query = KinRelationshipQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        a_id = query.validated_data["a"]
        b_id = query.validated_data["b"]

        existing_sheet_ids = set(
            CharacterSheet.objects.filter(pk__in=(a_id, b_id)).values_list("pk", flat=True)
        )
        if a_id not in existing_sheet_ids or b_id not in existing_sheet_ids:
            raise NotFound

        nodes_by_sheet_id = {
            node.sheet_id: node for node in Kinsperson.objects.filter(sheet_id__in=(a_id, b_id))
        }
        node_a = nodes_by_sheet_id.get(a_id)
        node_b = nodes_by_sheet_id.get(b_id)
        label = (
            None
            if node_a is None or node_b is None
            else derive_relationship(node_a, node_b, _viewer_entry(request))
        )
        return Response(KinRelationshipSerializer({"label": label}).data)
