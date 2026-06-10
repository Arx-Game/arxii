"""Vitals system API views."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.fatigue.services import get_full_status
from world.roster.models import RosterEntry
from world.vitals.constants import DERIVED_STATUS_ALIVE
from world.vitals.serializers import CharacterVitalsSerializer
from world.vitals.services import derive_character_status


class CharacterVitalsView(APIView):
    """Read-only vitals payload for the character sheet page (#521).

    Visibility: staff, or an account with an active tenure on the character.
    Everyone else receives 404 (same queryset rule as CharacterAnimaViewSet).

    Hot path rides the SharedMemoryModel identity map: the sheet is resolved
    by pk and vitals/fatigue are read via the instance-cached reverse
    accessors — repeated calls re-query none of those rows.
    """

    permission_classes = [IsAuthenticated]

    def _can_view(self, request: Request, character_id: int) -> bool:
        if request.user.is_staff:
            return True
        user = cast(AccountDB, request.user)
        owned_ids = set(RosterEntry.objects.for_account(user).character_ids())
        return character_id in owned_ids

    @extend_schema(responses=CharacterVitalsSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        if not self._can_view(request, character_id):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            vitals = sheet.vitals
            health = vitals.health
            max_health = vitals.max_health
            health_percentage = vitals.health_percentage
            wound_description = vitals.wound_description
            vitals_status = derive_character_status(sheet)
        except ObjectDoesNotExist:
            health = 0
            max_health = 0
            health_percentage = 0.0
            wound_description = ""
            vitals_status = DERIVED_STATUS_ALIVE

        fatigue_pool = getattr(sheet, "fatigue", None)  # noqa: GETATTR_LITERAL
        payload = {
            "health": health,
            "max_health": max_health,
            "health_percentage": health_percentage,
            "wound_description": wound_description,
            "status": vitals_status,
            "fatigue": get_full_status(sheet, pool=fatigue_pool),
        }
        return Response(CharacterVitalsSerializer(payload).data)
