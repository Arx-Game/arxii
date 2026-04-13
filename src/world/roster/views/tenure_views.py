"""Views for roster tenures."""

from http import HTTPMethod

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.roster.filters import RosterTenureFilterSet
from world.roster.models import RosterTenure
from world.roster.serializers import RosterTenureLookupSerializer


class RosterTenurePagination(PageNumberPagination):
    """Pagination for tenure search results."""

    page_size = 20


class RosterTenureViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """List roster tenures with search support."""

    serializer_class = RosterTenureLookupSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = RosterTenurePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RosterTenureFilterSet

    def get_queryset(self) -> QuerySet[RosterTenure]:
        """Return tenures with related data."""
        return RosterTenure.objects.select_related(
            "roster_entry__character_sheet__character",
        ).order_by("-start_date")

    @action(detail=False, methods=[HTTPMethod.GET], url_path="mine")
    def mine(self, request: Request) -> Response:
        """Return current user's active tenures for dropdown selection."""
        try:
            player_data = request.user.player_data
            tenures = player_data.cached_active_tenures
            # Filter only tenures from active rosters
            active_tenures = [tenure for tenure in tenures if tenure.roster_entry.roster.is_active]
            serializer = self.get_serializer(active_tenures, many=True)
            return Response(serializer.data)
        except AttributeError:
            # User has no player_data
            return Response([])
