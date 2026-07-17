"""Kinship API views (#2062).

Read surfaces only: families, the viewer-aware tree, and the CG slot
browser. Graph WRITES go through the kinship services from CG finalization
and staff admin — never generic REST mutation (the truth/record layer and
canon gating make open CRUD wrong here).
"""

from http import HTTPMethod
from typing import cast

from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.roster.filters import FamilyFilterSet
from world.roster.models import Family
from world.roster.serializers import (
    FamilySerializer,
    FamilyTreeSerializer,
    KinSlotPoolSerializer,
    KinSlotSerializer,
)
from world.roster.services.kinship import OMNISCIENT, family_tree_for, open_slots_for


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

    queryset = Family.objects.filter(is_playable=True).order_by("family_type", "name")
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
