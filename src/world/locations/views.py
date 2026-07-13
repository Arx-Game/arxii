"""API views for the locations system (#1522, #2222).

The per-character comfort read: the web face of the ``comfort`` command. Comfort is *personal*
(it depends on what you're wearing, your wards, and your injuries), so the endpoint only serves
the requesting account's own characters.

The portal-destinations read (#2222) follows the identical character-scoping shape: a
``?character_id=`` query param validated as owned by the requesting account via the roster
tenure system (mirrors ``ComfortViewSet``, the closest sibling in this app).
"""

from __future__ import annotations

from typing import cast

from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.locations.character_comfort import character_comfort_summary
from world.locations.serializers import (
    CharacterComfortSerializer,
    ComfortRequestSerializer,
    PortalDestinationSerializer,
    PortalDestinationsRequestSerializer,
)
from world.roster.models import RosterEntry

# Repeated failure detail, extracted to satisfy S1192 (duplicate string literals).
_CHARACTER_NOT_FOUND_MSG = "Character not found."


@extend_schema(tags=["comfort"])
class ComfortViewSet(viewsets.ViewSet):
    """Read-only per-character comfort. Personal data — only the requesting account's characters."""

    serializer_class = CharacterComfortSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="character_id",
                type=int,
                required=True,
                description="ObjectDB id of the character to read comfort for (must be your own).",
            )
        ],
        responses=CharacterComfortSerializer,
    )
    def summary(self, request: Request) -> Response:
        """GET /summary/?character_id=<id> — how uncomfortable that character is, and why."""
        request_params = ComfortRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        character_id = request_params.validated_data["character_id"]

        user = cast(AccountDB, request.user)
        # Comfort is personal: only serve a character the requesting account actually plays.
        # character_id == character_sheet_id by construction (CharacterSheet.character is a
        # primary-key OneToOne to ObjectDB), so the tenure check doubles as the ownership gate.
        owned = RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id)
        if not owned.exists():
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        sheet = CharacterSheet.objects.filter(pk=character_id).first()
        if sheet is None:
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        summary = character_comfort_summary(sheet.character)
        return Response(CharacterComfortSerializer(summary).data)


class PortalDestinationsPagination(PageNumberPagination):
    """Small default page — a character's reachable anchor network is not expected to be huge."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


@extend_schema(tags=["locations"])
class PortalDestinationsViewSet(viewsets.ViewSet):
    """Read-only: portal-network destinations reachable by a character right now (#2222).

    List-only — discovery, not action dispatch (travel itself rides the existing
    ``travel_to`` action, unchanged by this endpoint). Personal like comfort: only serves a
    character the requesting account actually plays.
    """

    serializer_class = PortalDestinationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PortalDestinationsPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="character_id",
                type=int,
                required=True,
                description="ObjectDB id of the character to read destinations for (must be "
                "your own).",
            )
        ],
        responses=PortalDestinationSerializer,
    )
    def list(self, request: Request) -> Response:
        """GET /?character_id=<id> — every anchor that character could portal-travel to now.

        Rides ``world.magic.services.portal_travel.portal_destinations`` unmodified — the
        service already applies the full leak-safe visibility contract (anchor kinds narrowed
        to the character's known travel techniques; a locked anchor visible only with
        owner/tenant standing at its room; the current room's own anchors excluded, since
        that's not a destination). This view adds no filtering of its own.
        """
        request_params = PortalDestinationsRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        character_id = request_params.validated_data["character_id"]

        user = cast(AccountDB, request.user)
        # Personal like comfort: only serve a character the requesting account actually plays.
        owned = RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id)
        if not owned.exists():
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        sheet = CharacterSheet.objects.filter(pk=character_id).first()
        if sheet is None:
            return Response({"detail": _CHARACTER_NOT_FOUND_MSG}, status=status.HTTP_404_NOT_FOUND)

        from world.magic.services.portal_travel import portal_destinations  # noqa: PLC0415

        destinations = portal_destinations(sheet.character)

        paginator = self.pagination_class()
        # DRF paginators accept any sized iterable at runtime; the stubs demand a QuerySet
        # (same suppression as the list-paginating catalog views in world/items/views.py).
        page = paginator.paginate_queryset(destinations, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = PortalDestinationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
