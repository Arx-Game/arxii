"""
Roster listing views.
"""

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, BasePermission

from world.roster.models import Roster
from world.roster.permissions import StaffOnlyWrite
from world.roster.serializers import RosterListSerializer


class RosterViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for listing rosters."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = Roster.objects.filter(is_active=True).order_by("sort_order", "name")
    serializer_class = RosterListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self) -> QuerySet[Roster]:
        # is_public gates visibility (#2728) — FROZEN/NPC are is_active=True (their
        # characters still resolve normally) but is_public=False, so anonymous/non-staff
        # callers must not see those shelves listed. Staff see every active roster.
        queryset = super().get_queryset()
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(is_public=True)

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ["list", "retrieve"]:
            # Allow anyone to list/retrieve rosters
            permission_classes = [AllowAny]
        else:
            permission_classes = [StaffOnlyWrite]
        return [permission() for permission in permission_classes]
