"""Fatigue system API views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.fatigue.services import (
    get_full_status,
    rest,
)
from world.roster.models import RosterEntry


def _get_character_sheet(request: Request) -> CharacterSheet | None:
    """Resolve the active character sheet for the authenticated user."""
    entry = RosterEntry.objects.for_account(request.user).first()
    if not entry:
        return None
    if entry.character_sheet_id is None:
        return None
    return entry.character_sheet


class FatigueStatusView(APIView):
    """Get current fatigue status for the player's active character."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sheet = _get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": "No active character."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = get_full_status(sheet)
        return Response(data)


class RestView(APIView):
    """Rest command: spend AP for Well Rested bonus."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        sheet = _get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": "No active character."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = rest(sheet)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})
