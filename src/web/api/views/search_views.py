"""Search-related API views."""

from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from evennia_extensions.models import RoomProfile
from world.missions.constants import GiverKind
from world.missions.target_queries import environmental_detail_candidates
from world.roster.models import RosterEntry


class OnlineCharacterSearchAPIView(APIView):
    """Return characters online and visible to the request user."""

    def get(self, request, *args, **kwargs):
        """Return list of online characters matching search term."""
        # Autocomplete endpoint returning custom dicts, not a model queryset
        term = request.query_params.get("search", "")  # noqa: USE_FILTERSET
        connected = AccountDB.objects.get_connected_accounts()
        qs = RosterEntry.objects.filter(tenures__player_data__account__in=connected)
        if term:
            qs = qs.filter(character__db_key__icontains=term)
        names = (
            qs.values_list("character__db_key", flat=True).distinct().order_by("character__db_key")
        )
        data = [{"value": name, "label": name} for name in names]
        return Response(data)


class RoomCharacterSearchAPIView(APIView):
    """Return characters in the caller's room visible to them."""

    def get(self, request, *args, **kwargs):
        """Return list of room occupants matching search term."""
        # In-memory scene state iteration, not a queryset
        term = request.query_params.get("search", "").lower()  # noqa: USE_FILTERSET
        puppets = request.user.get_puppeted_characters()
        if not puppets:
            return Response([])

        caller = puppets[0]
        caller_state = caller.scene_state
        if caller_state is None:
            return Response([])

        room_state = caller.location.scene_state
        if room_state is None:
            return Response([])

        results = []
        for obj_state in room_state.contents:
            if not obj_state.obj.is_typeclass(
                "typeclasses.characters.Character",
                exact=False,
            ):
                continue
            name = obj_state.get_display_name(looker=caller_state)
            if not term or term in name.lower():
                results.append({"value": name, "label": name})
        return Response(results)


class MissionGiverTargetSearchAPIView(APIView):
    """Staff-only search for MissionGiver.target candidates (#882).

    Results are constrained per ``kind`` to the same typeclass shape
    ``MissionGiver.clean()`` enforces (world/missions/models.py): ROOM_TRIGGER
    offers Room rows via the RoomProfile 1:1 (every Room gets one at creation,
    so no separate typeclass check is needed here); ENVIRONMENTAL_DETAIL uses
    ``environmental_detail_candidates()``, which mirrors the same
    Character/Room/Exit exclusion ``clean()`` enforces.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    RESULT_CAP = 20

    def get(self, request, *args, **kwargs):
        """Return matching {id, name, hint} rows, or a single row for ?id=."""
        kind = request.query_params.get("kind", "")  # noqa: USE_FILTERSET
        if kind not in (GiverKind.ROOM_TRIGGER, GiverKind.ENVIRONMENTAL_DETAIL):
            return Response(
                {"detail": "kind must be 'room_trigger' or 'environmental_detail'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_id = request.query_params.get("id")  # noqa: USE_FILTERSET
        term = request.query_params.get("search", "")  # noqa: USE_FILTERSET

        if kind == GiverKind.ROOM_TRIGGER:
            rows = self._room_rows(target_id, term)
        else:
            rows = self._environmental_detail_rows(target_id, term)

        if target_id is not None:
            if not rows:
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(rows[0])
        return Response(rows)

    def _room_rows(self, target_id: str | None, term: str) -> list[dict]:
        qs = RoomProfile.objects.select_related("objectdb", "area")
        if target_id is not None:
            qs = qs.filter(objectdb_id=target_id)
        elif term:
            qs = qs.filter(objectdb__db_key__icontains=term)
        qs = qs.order_by("objectdb__db_key")[: self.RESULT_CAP]
        return [
            {
                "id": rp.objectdb_id,
                "name": rp.objectdb.db_key,
                "hint": rp.area.name if rp.area_id else "",
            }
            for rp in qs
        ]

    def _environmental_detail_rows(self, target_id: str | None, term: str) -> list[dict]:
        qs = environmental_detail_candidates().select_related("db_location")
        if target_id is not None:
            qs = qs.filter(pk=target_id)
        elif term:
            qs = qs.filter(db_key__icontains=term)
        qs = qs.order_by("db_key")[: self.RESULT_CAP]
        return [
            {
                "id": obj.pk,
                "name": obj.db_key,
                "hint": obj.db_location.db_key if obj.db_location_id else "",
            }
            for obj in qs
        ]
