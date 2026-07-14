"""NPCAsset API (#1872, #2295).

Read endpoints for the player's own promoted assets, plus the introduce
action for voluntary co-ownership.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
    """Read endpoints for the player's own promoted assets + introduce action."""

    serializer_class = NPCAssetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NPCAssetPagination

    def get_queryset(self):
        persona = _active_persona_for_request(self.request)
        if persona is None:
            return NPCAsset.objects.none()
        return NPCAsset.objects.filter(promoter_persona=persona).select_related("asset_persona")

    @action(detail=False, methods=["post"])
    def introduce(self, request: Request) -> Response:
        """Introduce an owned asset to a co-present ally (#2295).

        POST /api/assets/introduce/ with asset_id + ally_persona_id.
        """
        from actions.registry import get_action  # noqa: PLC0415

        asset_id = request.data.get("asset_id")
        ally_persona_id = request.data.get("ally_persona_id")
        if asset_id is None or ally_persona_id is None:
            return Response(
                {"detail": "Both asset_id and ally_persona_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        puppet = request.user.puppet if hasattr(request.user, "puppet") else None
        if puppet is None:
            return Response(
                {"detail": "No puppeted character."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_obj = get_action("introduce_asset")
        result = action_obj.run(
            actor=puppet,
            asset_id=asset_id,
            ally_persona_id=ally_persona_id,
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": result.message}, status=status.HTTP_200_OK)
