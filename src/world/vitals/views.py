"""Vitals system API views."""

from __future__ import annotations

from typing import cast

from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.fatigue.services import get_full_status
from world.gm.permissions import HasGMTrust
from world.roster.models import RosterEntry
from world.scenes.models import Scene
from world.vitals.serializers import CharacterVitalsSerializer
from world.vitals.services import derive_character_status


class CharacterVitalsView(APIView):
    """Read-only vitals payload for the character sheet page (#521).

    Visibility: staff, an account with an active tenure on the character, or
    the GM of the character's active (non-battle) scene at JUNIOR+ trust
    (#3434). Everyone else receives 404 (same queryset rule as
    CharacterAnimaViewSet, which deliberately does NOT gain this carve-out —
    see docs/systems/INDEX.md's "Pool opacity" subsection).

    Hot path rides the SharedMemoryModel identity map: the sheet is resolved
    by pk and vitals/fatigue are read via the instance-cached reverse
    accessors — repeated calls re-query none of those rows.
    """

    permission_classes = [IsAuthenticated]

    def _can_view(self, request: Request, character_id: int) -> bool:
        """Staff, own-tenure, or the active scene's GM (ruling 2026-08-29, #3434).

        SUPERSEDES the 2026-08-08 #3071 ruling, which considered and rejected a
        ``viewer_can_gm`` carve-out here on the grounds that a scene's GM
        narrates off public wound text (badges, pose descriptions), not raw
        vitals numbers. #3434 is the fresh ruling #3071 asked for: it extends
        the carve-out to a scene's GM, matching the parity combat already
        grants (``CombatParticipantSerializer._can_view_vitals``,
        `world/combat/serializers.py:285`). The carve-out is narrower than
        combat's precedent in two ways combat doesn't enforce: it requires an
        *active* scene (battle-backed scenes are excluded — combat's own
        ``_can_view_vitals`` already serves vitals inside encounters) and at
        least JUNIOR GM trust (``HasGMTrust``, staff bypass preserved).
        """
        if request.user.is_staff:
            return True
        user = cast(AccountDB, request.user)
        if RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id).exists():
            return True
        return self._can_view_as_scene_gm(request, character_id)

    def _can_view_as_scene_gm(self, request: Request, character_id: int) -> bool:
        """The #3434 scene-GM carve-out — see ``_can_view``'s docstring.

        Note: ``Scene.has_character_present`` reads the room's *current*
        contents, so "target present in that scene" is location-derived, not
        participation-derived — a participant who steps out of the room drops
        out of the carve-out the moment they leave, even mid-scene. That is
        deliberately stricter than combat's precedent (which never checks
        scene state at all) — do not "fix" this by switching to a
        participation-based check.
        """
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            return False
        location = sheet.character.location
        if location is None:
            return False
        scene = Scene.objects.active_for_room(location).first()
        if scene is None or not scene.is_gm(request.user):
            return False
        if not HasGMTrust().has_permission(request, self):
            return False
        return scene.has_character_present({character_id})

    @extend_schema(responses=CharacterVitalsSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        if not self._can_view(request, character_id):
            raise NotFound
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            raise NotFound from None

        vitals = sheet.vitals_or_none
        if vitals is not None:
            health = vitals.health
            max_health = vitals.max_health
            health_percentage = vitals.health_percentage
            wound_description = vitals.wound_description
        else:
            health = 0
            max_health = 0
            health_percentage = 0.0
            wound_description = ""
        vitals_status = derive_character_status(sheet)

        fatigue_pool = sheet.fatigue_or_none
        payload = {
            "health": health,
            "max_health": max_health,
            "health_percentage": health_percentage,
            "wound_description": wound_description,
            "status": vitals_status,
            "fatigue": get_full_status(sheet, pool=fatigue_pool),
        }
        return Response(CharacterVitalsSerializer(payload).data)
