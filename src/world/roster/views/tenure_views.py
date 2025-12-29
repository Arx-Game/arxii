"""Views for roster tenures."""

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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

    def get_queryset(self):
        """Return tenures filtered by character name if provided."""
        qs = RosterTenure.objects.select_related("roster_entry__character")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(roster_entry__character__db_key__icontains=search)
        return qs.order_by("-start_date")

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
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
