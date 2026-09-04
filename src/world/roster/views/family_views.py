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
