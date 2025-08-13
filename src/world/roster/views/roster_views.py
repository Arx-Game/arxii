"""
Roster listing views.
"""

from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from world.roster.models import Roster
from world.roster.permissions import StaffOnlyWrite
from world.roster.serializers import RosterListSerializer


class RosterViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for listing rosters."""

    queryset = Roster.objects.filter(is_active=True).order_by("sort_order", "name")
    serializer_class = RosterListSerializer
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            # Allow anyone to list/retrieve rosters
            permission_classes = [AllowAny]
        else:
            permission_classes = [StaffOnlyWrite]
        return [permission() for permission in permission_classes]
