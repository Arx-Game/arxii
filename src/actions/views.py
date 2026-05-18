"""Views for the actions API."""

from django.shortcuts import get_object_or_404
from evennia.objects.models import ObjectDB
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from actions.player_interface import get_player_actions
from actions.serializers import PlayerActionSerializer
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
