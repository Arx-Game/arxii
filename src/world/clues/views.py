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
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from world.clues.filters import HeldClueFilter
from world.clues.models import CharacterClue
from world.clues.serializers import HeldClueSerializer
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from django.db.models import QuerySet


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
