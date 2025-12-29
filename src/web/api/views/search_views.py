"""Search-related API views."""

from evennia.accounts.models import AccountDB
from rest_framework.response import Response
from rest_framework.views import APIView

from world.roster.models import RosterEntry


class OnlineCharacterSearchAPIView(APIView):
    """Return characters online and visible to the request user."""

    def get(self, request, *args, **kwargs):
        """Return list of online characters matching search term."""
        term = request.query_params.get("search", "")
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
        term = request.query_params.get("search", "").lower()
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
