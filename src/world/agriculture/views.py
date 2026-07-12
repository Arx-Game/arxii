"""Agriculture API views — the web face of food collection (#2237)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from actions.definitions.collect_food import CollectFoodAction


class CollectFoodView(APIView):
    """Collect food from a Field into its domain's stockpile.

    Web dispatch of ``CollectFoodAction``: the body names the Field feature by
    ``field_instance_id``; the Action resolves it (the REST path does no
    ObjectDB resolution) and lands the food. Mirrors ``fatigue.RestView``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not hasattr(request.user, "player_data"):
            return Response({"detail": "No active character."}, status=status.HTTP_404_NOT_FOUND)
        current_character = request.user.player_data.get_current_character()
        if not current_character:
            return Response({"detail": "No active character."}, status=status.HTTP_404_NOT_FOUND)

        field_instance_id = request.data.get("field_instance_id")
        result = CollectFoodAction().run(
            actor=current_character, field_instance_id=field_instance_id
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message, **result.data})
