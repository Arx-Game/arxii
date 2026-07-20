"""API views for the worship foundation (#2355)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.stories.pagination import StandardResultsSetPagination
from world.worship.models import Miracle, WorshippedBeing
from world.worship.serializers import MiracleSerializer, WorshippedBeingRefSerializer


class WorshippedBeingViewSet(ReadOnlyModelViewSet):
    """Public catalog of active worshippable beings (the CG picker source).

    Exposes only the reference shape (id, name, tradition name) — pools,
    avatars, and worshipper lists never leave this endpoint.
    """

    serializer_class = WorshippedBeingRefSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["tradition"]
    search_fields = ["name"]
    queryset = WorshippedBeing.objects.filter(is_active=True).select_related("tradition")


class MiracleViewSet(ReadOnlyModelViewSet):
    """Staff-facing miracle catalog browser (#2360)."""

    serializer_class = MiracleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = Miracle.objects.select_related("being")
