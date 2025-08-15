"""Views for roster tenures."""

from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

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
