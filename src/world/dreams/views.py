"""Dreams system API views (#3003)."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.dreams.engagement import is_dream_engaged
from world.dreams.models import DreamReflection
from world.dreams.serializers import DreamStateSerializer
from world.dreams.services import co_dreamers_for, dreamspace_for, dreamwalk_candidates_for
from world.roster.models import RosterEntry
from world.vitals.services import perceives_dreamside


def _character_ref(sheet: CharacterSheet) -> dict[str, object]:
    """The ``{id, name}`` shape every character reference in the payload uses."""
    return {"id": sheet.pk, "name": sheet.display_ic()}


class CharacterDreamStateView(APIView):
    """Read-only dream-state payload for the dreamspace panel (#3003).

    Visibility: staff, or an account with an active tenure on the character.
    Everyone else receives 404 (same queryset rule as CharacterVitalsView) —
    a 403 would confirm the character exists.
    """

    permission_classes = [IsAuthenticated]

    def _can_view(self, request: Request, character_id: int) -> bool:
        if request.user.is_staff:
            return True
        user = cast(AccountDB, request.user)
        return (
            RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id).exists()
        )

    @extend_schema(responses=DreamStateSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        if not self._can_view(request, character_id):
            raise NotFound
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            raise NotFound from None

        room = dreamspace_for(sheet)
        dream_room = None
        if room is not None:
            dream_room = {
                "id": room.pk,
                "key": room.key,
                "description": room.item_data.get_display_description(),
            }

        character = sheet.character
        location = character.location if character is not None else None
        reflection = DreamReflection.objects.for_waking_room(location)
        descent_target = reflection.descent_target if reflection is not None else None
        can_descend = descent_target is not None
        descent_name = descent_target.objectdb.key if descent_target is not None else ""
        can_ascend = (
            location is not None
            and DreamReflection.objects.filter(
                descent_target_id=location.pk,
                is_active=True,
            ).exists()
        )

        try:
            presence = sheet.dreamwalk_presence
        except ObjectDoesNotExist:
            presence = None
        dreamwalk_host = _character_ref(presence.host) if presence is not None else None

        payload = {
            "is_dreamside": perceives_dreamside(sheet),
            "dream_room": dream_room,
            "co_dreamers": [_character_ref(s) for s in co_dreamers_for(sheet)],
            "dreamwalk_host": dreamwalk_host,
            "dreamwalk_candidates": [_character_ref(s) for s in dreamwalk_candidates_for(sheet)],
            "can_descend": can_descend,
            "descent_name": descent_name,
            "can_ascend": can_ascend,
            "wake_blocked": is_dream_engaged(sheet),
        }
        return Response(DreamStateSerializer(payload).data)
