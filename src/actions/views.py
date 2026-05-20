"""Views for the actions API."""

from django.shortcuts import get_object_or_404
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from actions.errors import ActionDispatchError
from actions.player_interface import dispatch_player_action, get_player_actions
from actions.serializers import (
    DispatchActionSerializer,
    DispatchResultSerializer,
    PlayerActionSerializer,
)
from actions.types import PlayerAction
from web.api.permissions import IsCharacterOwner


class ActionsPagination(PageNumberPagination):
    """Standard pagination for actions endpoints."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AvailableActionsView(ListAPIView):
    """Available actions for a character — merged challenge + combat backends.

    Returns all PlayerAction descriptors available to the character right now.
    Recomputed on every request; no caching.
    """

    serializer_class = PlayerActionSerializer
    permission_classes = [IsAuthenticated, IsCharacterOwner]
    pagination_class = ActionsPagination

    def get_queryset(self) -> list[PlayerAction]:
        character = get_object_or_404(ObjectDB, pk=self.kwargs["character_id"])
        return get_player_actions(character)


class DispatchActionView(APIView):
    """Dispatch a player action — the unified 'do the thing' surface.

    POST ``{ref: {...}, kwargs: {...}}`` to execute an action for the character.
    The ref is validated by ``DispatchActionSerializer`` (which constructs an
    ``ActionRef`` and enforces backend↔id constraints).  The validated ref is
    then passed to ``dispatch_player_action`` which validates it against the
    character's current availability (stale/forged-ref safety) and routes to
    the appropriate backend.

    ``ActionDispatchError`` from ``dispatch_player_action`` is caught here and
    surfaced as a 400 with ``exc.user_message`` — mirroring the ``resolve_round``
    view pattern (the only sanctioned typed-error→user_message boundary handler).
    Input-shape validation lives entirely in ``DispatchActionSerializer``; this
    view never inspects ``request.data`` directly.
    """

    permission_classes = [IsAuthenticated, IsCharacterOwner]

    def post(self, request: Request, character_id: int) -> Response:
        """Dispatch the given action ref for character_id."""
        character = get_object_or_404(ObjectDB, pk=character_id)

        serializer = DispatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ref = serializer.validated_data["ref"]
        kwargs = serializer.validated_data["kwargs"]

        try:
            result = dispatch_player_action(character, ref, kwargs)
        except ActionDispatchError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DispatchResultSerializer(result).data, status=status.HTTP_200_OK)
