"""Companion API views (#672).

Read-only surface mirroring world/ships/views.py's ShipViewSet: writes
(binding) stay on action.run() via BindCompanionAction (Task 8) — no write
endpoint exists here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from world.companions.filters import CompanionFilterSet
from world.companions.models import Companion, CompanionArchetype
from world.companions.serializers import CompanionArchetypeSerializer, CompanionSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


class CompanionPagination(PageNumberPagination):
    page_size = 50


def _active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or None if unresolvable.

    Mirrors world.ships.views._active_persona_for_request.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class CompanionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read endpoints for the player's own active companions."""

    serializer_class = CompanionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CompanionPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CompanionFilterSet

    def get_queryset(self):
        persona = _active_persona_for_request(self.request)
        if persona is None:
            return Companion.objects.none()
        return Companion.objects.filter(
            owner=persona.character_sheet, released_at__isnull=True
        ).select_related("archetype")


class CompanionArchetypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only catalog of authored CompanionArchetype rows."""

    queryset = CompanionArchetype.objects.all()
    serializer_class = CompanionArchetypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
