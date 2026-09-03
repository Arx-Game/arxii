"""API views for the clue read surface (#1575).

The held-clue journal — what a character has discovered. Clues are **private IC knowledge**: a
player only ever sees clues held by characters they play (``RosterEntry.objects.for_account``),
never another player's. The backend clue model + acquisition/discovery services (#1143) already
exist; this is purely the read/browse surface over them. (Active research "pursuit" tracking is a
separate, later layer.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.clues.filters import HeldClueFilter
from world.clues.models import CharacterClue, Clue
from world.clues.serializers import ClueSearchResultSerializer, HeldClueSerializer
from world.clues.services import RESOLVABLE_CLUE_TARGET_KINDS, clue_target_kind_allowed
from world.gm.permissions import IsGMOrStaff
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


@extend_schema(tags=["clues"])
class MyHeldCluesView(ListAPIView):
    """List the clues held by the requesting player's characters (#1575).

    Newest first. Always scoped to characters the requester plays — a foreign or unknown
    ``character_sheet`` filter simply returns nothing (no existence leak).
    """

    serializer_class = HeldClueSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = HeldClueFilter

    def get_queryset(self) -> QuerySet[CharacterClue]:
        user = cast(AccountDB, self.request.user)
        return (
            CharacterClue.objects.filter(roster_entry__in=RosterEntry.objects.for_account(user))
            .select_related("clue", "roster_entry")
            .order_by("-found_at")
        )


@extend_schema(
    tags=["clues"],
    parameters=[OpenApiParameter("q", str, required=False)],
    responses=ClueSearchResultSerializer(many=True),
)
class ClueSearchView(APIView):
    """GM-only clue search for the stake reward picker (#3566).

    Only clues whose target kind ``AUTOMATIC`` resolution can actually deliver on its
    own (``RESOLVABLE_CLUE_TARGET_KINDS``) are searchable: an ITEM-target clue is a
    bare pointer, not a coherent reward payload. Rows are further filtered through
    ``clue_target_kind_allowed`` so a GM never sees a clue whose target they aren't
    permitted to author (SECRET targets stay staff-only).
    """

    permission_classes = [IsAuthenticated, IsGMOrStaff]

    def get(self, request: Request) -> Response:
        # A FilterSet only narrows the queryset, but this view's second pass
        # (clue_target_kind_allowed) is a per-row Python permission check, not a
        # queryset filter, so a FilterSet class would still need this same
        # request.query_params reach-in; one ad hoc `q` param isn't worth the split.
        q = request.query_params.get("q", "")  # noqa: USE_FILTERSET
        # Apply the per-account target-kind policy to the queryset itself, before the
        # top-25 slice, so an alphabetically-early run of disallowed clues (e.g.
        # SECRET targets a non-staff GM can't see) can't starve out allowed matches
        # further down the sort (#3566 fix-round finding).
        allowed_kinds = [
            kind
            for kind in RESOLVABLE_CLUE_TARGET_KINDS
            if clue_target_kind_allowed(request.user, kind)
        ]
        queryset = Clue.objects.filter(target_kind__in=allowed_kinds)
        if q:
            queryset = queryset.filter(name__icontains=q)
        rows = queryset.order_by("name")[:25]
        serializer = ClueSearchResultSerializer(rows, many=True)
        return Response(serializer.data)
