"""Tarot card views."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.tarot.models import TarotCard
from world.tarot.serializers import TarotCardSerializer


class TarotCardViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of tarot cards for CG surname selection."""

    serializer_class = TarotCardSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Return all 78 cards without pagination
    filter_backends = []

    def get_queryset(self):
        return TarotCard.objects.all()
