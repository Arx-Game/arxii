"""Action-points read API (#1446)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.action_points.models import ActionPointPool
from world.action_points.serializers import ActionPointPoolSerializer
from world.character_sheets.models import CharacterSheet
from world.roster.models import RosterEntry


class ActionPointPoolView(APIView):
    """Read-only AP pool for the status surfaces (#1446).

    Visibility: staff, or an account with an active tenure on the character.
    Everyone else receives 404 (the vitals-view rule). Pools lazy-create with
    config defaults so a fresh character still reads cleanly. ``current`` is
    the authoritative "AP remaining" — the weekly cron tops it up additively.
    """

    permission_classes = [IsAuthenticated]

    def _can_view(self, request: Request, character_id: int) -> bool:
        if request.user.is_staff:
            return True
        return (
            RosterEntry.objects.for_account(request.user)
            .filter(character_sheet_id=character_id)
            .exists()
        )

    @extend_schema(responses=ActionPointPoolSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        if not self._can_view(request, character_id):
            raise NotFound
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            # Guards the staff path: a bare ObjectDB pk (a vase, a room) must never
            # lazy-create a junk ActionPointPool row.
            raise NotFound from None
        pool = ActionPointPool.get_or_create_for_character(sheet.character)
        payload = {
            "current": pool.current,
            "effective_maximum": pool.get_effective_maximum(),
            "banked": pool.banked,
        }
        return Response(ActionPointPoolSerializer(payload).data)
