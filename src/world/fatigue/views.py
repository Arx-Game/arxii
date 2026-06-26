"""Fatigue system API views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from actions.definitions.fatigue import RestAction


class RestView(APIView):
    """Rest command: spend AP for Well Rested bonus."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not hasattr(request.user, "player_data"):
            return Response(
                {"detail": "No active character."},
                status=status.HTTP_404_NOT_FOUND,
            )
        current_character = request.user.player_data.get_current_character()
        if not current_character:
            return Response(
                {"detail": "No active character."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = RestAction().run(actor=current_character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})
