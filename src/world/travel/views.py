"""API views for the overworld travel system (#2352)."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.travel.models import TravelHub, TravelMethod, Voyage, VoyageInvite
from world.travel.serializers import (
    TravelHubSerializer,
    TravelMethodSerializer,
    VoyageInviteSerializer,
    VoyageSerializer,
)


class TravelHubViewSet(viewsets.ReadOnlyModelViewSet):
    """List active travel hubs — public infrastructure (no per-char filtering)."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = TravelHubSerializer
    permission_classes = [IsAuthenticated]
    queryset = TravelHub.objects.filter(is_active=True)


class TravelMethodViewSet(viewsets.ReadOnlyModelViewSet):
    """List all travel methods."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = TravelMethodSerializer
    permission_classes = [IsAuthenticated]
    queryset = TravelMethod.objects.all()


class VoyageViewSet(viewsets.ReadOnlyModelViewSet):
    """List voyages the requesting user's personas participate in."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = VoyageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from world.travel.models import VoyageParticipant  # noqa: PLC0415

        user = self.request.user
        if not hasattr(user, "sheet_data"):
            return Voyage.objects.none()
        sheet = user.sheet_data
        if sheet is None:
            return Voyage.objects.none()
        persona_ids = VoyageParticipant.objects.filter(persona__character_sheet=sheet).values_list(
            "voyage_id", flat=True
        )
        return (
            Voyage.objects.filter(pk__in=persona_ids)
            .select_related("leader", "travel_method", "origin_hub", "destination_hub")
            .prefetch_related("participants", "invites")  # noqa: PREFETCH_STRING
        )


class VoyageInviteViewSet(viewsets.ReadOnlyModelViewSet):
    """List PENDING voyage invites targeting the requesting user's personas."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = VoyageInviteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, "sheet_data"):
            return VoyageInvite.objects.none()
        sheet = user.sheet_data
        if sheet is None:
            return VoyageInvite.objects.none()
        return VoyageInvite.objects.filter(
            target_persona__character_sheet=sheet,
            response=VoyageInvite.Response.PENDING,
        ).select_related("voyage", "target_persona", "invited_by")
