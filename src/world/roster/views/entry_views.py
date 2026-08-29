"""
RosterEntry views and related functionality.
"""

from http import HTTPMethod

from django.db.models import Count, Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.roster.filters import RosterEntryFilterSet
from world.roster.models import RosterEntry, RosterTenure, TenureMedia
from world.roster.models.choices import RosterType
from world.roster.permissions import IsPlayerOrStaff
from world.roster.serializers import (
    MyRosterEntrySerializer,
    RosterApplicationCreateSerializer,
    RosterApplicationSerializer,
    RosterEntrySerializer,
    SelectedEntryResultSerializer,
    SelectEntryRequestSerializer,
)
from world.roster.services.selection import SelectionError, set_selected_entry


class RosterEntryPagination(PageNumberPagination):
    """Default pagination for roster entries."""

    page_size = 20


class RosterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Expose roster entries and related actions."""

    serializer_class = RosterEntrySerializer
    permission_classes = [
        AllowAny,
    ]  # Read-only viewset, so AllowAny is fine for listing/viewing
    filter_backends = [DjangoFilterBackend]
    filterset_class = RosterEntryFilterSet
    pagination_class = RosterEntryPagination

    def get_queryset(self) -> QuerySet[RosterEntry]:
        """Return a queryset of roster entries.

        NPC-shelf entries are excluded from general visibility (#3426): staff
        always see every entry; a non-staff caller sees an NPC-shelf entry
        only when they hold an active tenure on it (their own Story NPC).
        ``RosterViewSet`` already hides the NPC *shelf itself*
        (``Roster.is_public=False``) from anonymous/non-staff shelf listings
        (#2728) -- this closes the companion gap where individual
        ``RosterEntry`` rows on that shelf were still reachable regardless,
        via this AllowAny viewset, outing an unrevealed story's cast.
        """

        queryset = (
            RosterEntry.objects.select_related(
                "character_sheet",
                "character_sheet__character",
                "roster",
            )
            .prefetch_related(
                Prefetch(
                    "tenures",
                    queryset=RosterTenure.objects.all().prefetch_related(
                        Prefetch(
                            "media",
                            queryset=TenureMedia.objects.select_related("media"),
                            to_attr="cached_media",
                        ),
                    ),
                    to_attr="cached_tenures",
                ),
            )
            .order_by("character_sheet__character__db_key")
        )

        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return queryset

        hidden_npc_entries = Q(roster__roster_type=RosterType.NPC)
        if user.is_authenticated:
            try:
                player_data = user.player_data
            except AttributeError:
                player_data = None
            if player_data is not None:
                own_npc_entry_ids = RosterTenure.objects.filter(
                    player_data=player_data,
                    start_date__isnull=False,
                    end_date__isnull=True,
                ).values_list("roster_entry_id", flat=True)
                hidden_npc_entries &= ~Q(pk__in=own_npc_entry_ids)
        return queryset.exclude(hidden_npc_entries)

    def get_serializer_class(self) -> type[BaseSerializer]:
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
    def mine(self, request: Request) -> Response:
        """Return roster entries for characters owned by the account.

        Annotates ``unread_narrative_count`` (#3412 — the Hall) — unacknowledged
        ``NarrativeMessageDelivery`` rows per character, via a single aggregated
        JOIN/GROUP BY rather than a per-row query.
        """

        # Get characters through PlayerData model
        try:
            player_data = request.user.player_data
            available_characters = player_data.get_available_characters()
        except AttributeError:
            available_characters = []

        entries = (
            RosterEntry.objects.filter(
                character_sheet__character__in=available_characters,
            )
            .select_related("roster")
            .annotate(
                unread_narrative_count=Count(
                    "character_sheet__narrative_message_deliveries",
                    filter=Q(
                        character_sheet__narrative_message_deliveries__acknowledged_at__isnull=True,
                    ),
                ),
            )
        )
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=SelectEntryRequestSerializer,
        responses={200: SelectedEntryResultSerializer},
        tags=["roster"],
    )
    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        permission_classes=[IsAuthenticated],
    )
    def select(self, request: Request) -> Response:
        """#3412 — set/clear the account's durable character selection (state 2.5).

        Selection is NOT presence: this triggers zero lifecycle, session, or
        puppeting side effects. The chosen entry must be one of the account's
        own current roster entries (mirrors ``mine``'s queryset); a foreign or
        unknown id is rejected uniformly, mirroring the persona set-active
        endpoint. ``entry_id: null`` always clears.
        """
        body = SelectEntryRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        entry_id = body.validated_data["entry_id"]
        try:
            player_data = request.user.player_data
        except AttributeError:
            msg = "Account has no player data."
            raise serializers.ValidationError(msg) from None

        entry = None
        if entry_id is not None:
            entry = RosterEntry.objects.filter(pk=entry_id).first()
            if entry is None:
                msg = "That isn't one of your characters."
                raise serializers.ValidationError(msg)

        try:
            set_selected_entry(player_data, entry)
        except SelectionError as exc:
            raise serializers.ValidationError(exc.user_message) from exc

        return Response(SelectedEntryResultSerializer(player_data).data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsPlayerOrStaff],
    )
    def set_profile_picture(self, request: Request, pk: int | None = None) -> Response:
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
        methods=[HTTPMethod.POST],
        permission_classes=[IsAuthenticated],
        serializer_class=RosterApplicationSerializer,
    )
    def apply(self, request: Request, pk: int | None = None) -> Response:
        """Accept a play application for a roster entry's character."""

        # Check if user's email is verified
        try:
            player_data = request.user.player_data
            if not player_data.can_apply_for_characters():
                return Response(
                    {
                        "detail": ("Email verification required before applying for characters."),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        except AttributeError:
            return Response(
                {"detail": "Player data not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        roster_entry = self.get_object()
        message_serializer = self.get_serializer(data=request.data)
        message_serializer.is_valid(raise_exception=True)

        create_data = {
            "character_id": roster_entry.character_sheet.character.id,
            "application_text": message_serializer.validated_data["message"],
        }
        create_serializer = RosterApplicationCreateSerializer(
            data=create_data,
            context=self.get_serializer_context(),
        )
        create_serializer.is_valid(raise_exception=True)
        create_serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
