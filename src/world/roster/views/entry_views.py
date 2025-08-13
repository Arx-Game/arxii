"""
RosterEntry views and related functionality.
"""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from world.roster.filters import RosterEntryFilterSet
from world.roster.models import RosterEntry, RosterTenure, TenureMedia
from world.roster.permissions import IsPlayerOrStaff
from world.roster.serializers import (
    MyRosterEntrySerializer,
    RosterApplicationSerializer,
    RosterEntrySerializer,
)


class RosterEntryPagination(PageNumberPagination):
    """Default pagination for roster entries."""

    page_size = 20


class RosterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Expose roster entries and related actions."""

    serializer_class = RosterEntrySerializer
    permission_classes = [
        AllowAny
    ]  # Read-only viewset, so AllowAny is fine for listing/viewing
    filter_backends = [DjangoFilterBackend]
    filterset_class = RosterEntryFilterSet
    pagination_class = RosterEntryPagination

    def get_queryset(self):
        """Return a queryset of roster entries."""

        return (
            RosterEntry.objects.select_related("character")
            .prefetch_related(
                Prefetch(
                    "tenures",
                    queryset=RosterTenure.objects.all().prefetch_related(
                        Prefetch(
                            "media",
                            queryset=TenureMedia.objects.select_related("media"),
                            to_attr="cached_media",
                        )
                    ),
                )
            )
            .order_by("character__db_key")
        )

    def get_serializer_class(self):
        if self.action == "mine":
            return MyRosterEntrySerializer
        if self.action == "apply":
            return RosterApplicationSerializer
        return super().get_serializer_class()

    @action(
        detail=False,
        permission_classes=[IsAuthenticated],
        serializer_class=MyRosterEntrySerializer,
    )
    def mine(self, request):
        """Return roster entries for characters owned by the account."""

        # Get characters through PlayerData model
        try:
            player_data = request.user.player_data
            available_characters = player_data.get_available_characters()
        except AttributeError:
            available_characters = []

        entries = RosterEntry.objects.filter(character__in=available_characters)
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsPlayerOrStaff],
    )
    def set_profile_picture(self, request, pk=None):
        """Set the profile picture for this roster entry."""
        roster_entry = self.get_object()
        media_id = request.data.get("tenure_media_id")

        # Staff can access any tenure media, non-staff only their own
        if request.user.is_staff:
            media = TenureMedia.objects.get(
                pk=media_id,
                tenure__roster_entry=roster_entry,
            )
        else:
            media = TenureMedia.objects.get(
                pk=media_id,
                tenure__roster_entry=roster_entry,
                tenure__player_data=request.user.player_data,
            )

        roster_entry.profile_picture = media
        roster_entry.full_clean()
        roster_entry.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        serializer_class=RosterApplicationSerializer,
    )
    def apply(self, request, pk=None):
        """Accept a play application for a roster entry's character."""

        self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
