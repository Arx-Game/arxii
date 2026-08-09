"""Player-facing trap read surface (#3011) — the endpoint ``DisarmTrapAction``
(`actions/definitions/traps.py`) was missing: without a way to see a ``trap_id``,
the action was registered but unreachable.

Follows the ``ComfortViewSet``/``PortalDestinationsViewSet`` shape
(``world/locations/views.py``) exactly: a required ``?character_id=`` query param,
validated as owned by the requesting account via the roster tenure system. That
ownership check doubles as the "present in the room" gate here — the room isn't a
query param at all, it's derived from the owned character's actual
``ObjectDB.location``, so a caller can never ask for a room they don't currently
occupy.
"""

from __future__ import annotations

from typing import cast

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.room_features.models import Trap
from world.room_features.serializers_traps import RoomTrapRequestSerializer, TrapSerializer
from world.roster.models import RosterEntry

_CHARACTER_NOT_FOUND_MSG = "Character not found."


@extend_schema(tags=["room-features"])
class RoomTrapViewSet(viewsets.ViewSet):
    """List-only: armed traps visible to a character in their current room (#3011).

    Personal like comfort/portal-destinations: only serves a character the
    requesting account actually plays. Visibility leak table (per the #3011
    spec): armed traps that are ``is_hidden=False`` (authored obvious hazards,
    everyone sees them, #3011 gives this field its first readers) OR already in
    the viewer's own ``detected_by`` — never a hidden trap another character
    spotted, and never an unarmed (already-disarmed) trap.
    """

    serializer_class = TrapSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="character_id",
                type=int,
                required=True,
                description="ObjectDB id of the character to read visible room traps for "
                "(must be your own).",
            )
        ],
        responses=TrapSerializer(many=True),
    )
    def list(self, request: Request) -> Response:
        """GET /?character_id=<id> — armed traps that character can currently see."""
        request_params = RoomTrapRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        character_id = request_params.validated_data["character_id"]

        user = cast(AccountDB, request.user)
        # Personal like comfort/portal-destinations: only serve a character the
        # requesting account actually plays.
        owned = RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id)
        if not owned.exists():
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        sheet = CharacterSheet.objects.filter(pk=character_id).first()
        if sheet is None:
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        character = sheet.character
        if character.location is None:
            return Response([])

        traps = Trap.objects.filter(room_profile_id=character.location.pk, is_armed=True).filter(
            Q(is_hidden=False) | Q(detected_by=sheet)
        )
        serializer = TrapSerializer(traps, many=True)
        return Response(serializer.data)
