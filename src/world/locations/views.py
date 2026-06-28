"""API views for the locations system (#1522).

The per-character comfort read: the web face of the ``comfort`` command. Comfort is *personal*
(it depends on what you're wearing, your wards, and your injuries), so the endpoint only serves
the requesting account's own characters.
"""

from __future__ import annotations

from typing import cast

from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.locations.character_comfort import character_comfort_summary
from world.locations.serializers import CharacterComfortSerializer, ComfortRequestSerializer
from world.roster.models import RosterEntry


@extend_schema(tags=["comfort"])
class ComfortViewSet(viewsets.ViewSet):
    """Read-only per-character comfort. Personal data — only the requesting account's characters."""

    serializer_class = CharacterComfortSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="character_id",
                type=int,
                required=True,
                description="ObjectDB id of the character to read comfort for (must be your own).",
            )
        ],
        responses=CharacterComfortSerializer,
    )
    def summary(self, request: Request) -> Response:
        """GET /summary/?character_id=<id> — how uncomfortable that character is, and why."""
        request_params = ComfortRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        character_id = request_params.validated_data["character_id"]

        user = cast(AccountDB, request.user)
        # Comfort is personal: only serve a character the requesting account actually plays.
        # character_id == character_sheet_id by construction (CharacterSheet.character is a
        # primary-key OneToOne to ObjectDB), so the tenure check doubles as the ownership gate.
        owned = RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id)
        if not owned.exists():
            return Response({"detail": "Character not found."}, status=status.HTTP_404_NOT_FOUND)

        sheet = CharacterSheet.objects.filter(pk=character_id).first()
        if sheet is None:
            return Response({"detail": "Character not found."}, status=status.HTTP_404_NOT_FOUND)

        summary = character_comfort_summary(sheet.character)
        return Response(CharacterComfortSerializer(summary).data)
