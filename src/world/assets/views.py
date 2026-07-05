"""Read-only NPCAsset API (#1872).

Mirrors world/companions/views.py's ownership-scoping pattern exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from world.assets.models import NPCAsset
from world.assets.serializers import NPCAssetSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


class NPCAssetPagination(PageNumberPagination):
    page_size = 50


def _active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or None if unresolvable."""
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class NPCAssetViewSet(viewsets.ReadOnlyModelViewSet):
    """Read endpoints for the player's own promoted assets."""

    serializer_class = NPCAssetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NPCAssetPagination

    def get_queryset(self):
        persona = _active_persona_for_request(self.request)
        if persona is None:
            return NPCAsset.objects.none()
        return NPCAsset.objects.filter(promoter_persona=persona).select_related("asset_persona")
