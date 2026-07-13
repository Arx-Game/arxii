"""API views for ceremonies (#2289).

Read-only: ceremony verbs (open/offering/speech/finish/abandon) are REGISTRY
actions reached through the generic player-action dispatch seam, exactly like
telnet. This ViewSet feeds the room ceremony card.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.ceremonies.models import Ceremony
from world.ceremonies.serializers import CeremonySerializer
from world.stories.pagination import StandardResultsSetPagination


class CeremonyViewSet(ReadOnlyModelViewSet):
    """List/detail ceremonies, filterable by location and status."""

    serializer_class = CeremonySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    # location__objectdb lets the game view filter by the room object id it holds.
    filterset_fields = ["location", "location__objectdb", "status", "ceremony_type__key"]
    queryset = (
        Ceremony.objects.select_related("ceremony_type", "officiant", "presented_being", "location")
        # Bare-string prefetch is deliberate: Prefetch(to_attr=...) onto
        # SharedMemoryModel parents leaks across requests (identity map).
        .prefetch_related("honorees__honoree_sheet", "speeches__speaker")  # noqa: PREFETCH_STRING
        .order_by("-opened_at")
    )
