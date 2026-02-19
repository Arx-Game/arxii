"""Tarot card views."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.tarot.models import NamingRitualConfig, TarotCard
from world.tarot.serializers import NamingRitualConfigSerializer, TarotCardSerializer


class TarotCardViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of tarot cards for CG surname selection."""

    serializer_class = TarotCardSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Return all 78 cards without pagination
    filter_backends = []

    def get_queryset(self):
        return TarotCard.objects.all()


class NamingRitualConfigView(APIView):
    """Return the naming ritual configuration (flavor text + codex link)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        config = NamingRitualConfig.objects.first()
        if config:
            return Response(NamingRitualConfigSerializer(config).data)
        return Response(
            {
                "flavor_text": ("A Mirrormask draws from the Arcana to divine your name..."),
                "codex_entry_id": None,
            }
        )
