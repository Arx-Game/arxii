"""DRF views for the player channels API (#3299).

- ``channels/``: the channels the requester can reach right now (access re-derived from
  live state every request), each with the requester's own subscription; a detail
  ``identities/`` route lists the requester's own tenures eligible to speak there.
- ``subscriptions/``: the requester's own subscription rows (join, preferences, leave,
  mark read), through the channel services.
- ``messages/``: a channel's history (``?channel=`` required, newest first); posting and
  staff moderation run the account-authorized channel Actions, the same ones telnet's
  ``channel`` command runs (ADR-0001).
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.definitions.channels import (
    BanChannelAuthorAction,
    DeleteChannelMessageAction,
    PostToChannelAction,
)
from world.channels.filters import (
    ChannelFilterSet,
    ChannelMessageFilterSet,
    ChannelSubscriptionFilterSet,
)
from world.channels.models import Channel, ChannelMessage, ChannelSubscription
from world.channels.serializers import (
    ChannelActionResultSerializer,
    ChannelBanSerializer,
    ChannelIdentitySerializer,
    ChannelMessageCreateSerializer,
    ChannelMessageSerializer,
    ChannelSerializer,
    ChannelSubscriptionSerializer,
)
from world.channels.services import (
    accessible_channels_for,
    eligible_tenures,
    hidden_author_player_ids,
    mark_read,
    subscriptions_by_channel,
    unread_counts,
    unsubscribe,
)

_SUBSCRIPTION_TENURE = "display_tenure__roster_entry__character_sheet__character"


class ChannelViewSet(viewsets.ReadOnlyModelViewSet):
    """Channels the requester can read and post in."""

    serializer_class = ChannelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChannelFilterSet
    # Intrinsically small: the public channel, the requester's orgs, staff channels.
    pagination_class = None

    def get_queryset(self) -> QuerySet[Channel]:
        return accessible_channels_for(self.request.user)

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if self.request is None or not self.request.user.is_authenticated:
            return context
        subscriptions = subscriptions_by_channel(self.request.user)
        context["subscriptions"] = subscriptions
        context["unread_counts"] = unread_counts(self.request.user, list(subscriptions.values()))
        return context

    @extend_schema(responses=ChannelIdentitySerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def identities(self, request: Request, pk: str | None = None) -> Response:
        """Who the requester can speak as here: their own eligible tenures, by name."""
        channel = self.get_object()
        tenures = eligible_tenures(request.user, channel)
        return Response(ChannelIdentitySerializer(tenures, many=True).data)


class ChannelSubscriptionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """The requester's own channel subscriptions. PATCH only (no PUT)."""

    serializer_class = ChannelSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChannelSubscriptionFilterSet
    # Intrinsically small: one row per channel the requester joined.
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[ChannelSubscription]:
        queryset = ChannelSubscription.objects.filter(account=self.request.user).select_related(
            "channel__organization", _SUBSCRIPTION_TENURE
        )
        if self.action == "list":
            # A row outlives access (a player who left the org keeps it), but the list
            # shows only channels reachable now. Detail routes still find the row, so a
            # lost channel can be left or muted.
            queryset = queryset.filter(
                channel_id__in=accessible_channels_for(self.request.user).values("pk")
            )
        return queryset

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if self.action == "list" and self.request.user.is_authenticated:
            context["unread_counts"] = unread_counts(
                self.request.user, list(subscriptions_by_channel(self.request.user).values())
            )
        return context

    def perform_destroy(self, instance: ChannelSubscription) -> None:
        unsubscribe(self.request.user, instance.channel)

    @extend_schema(request=None, responses=ChannelSubscriptionSerializer)
    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request: Request, pk: str | None = None) -> Response:
        """Mark everything in this channel read for the requester."""
        subscription = self.get_object()
        mark_read(subscription)
        return Response(self.get_serializer(subscription).data)


class ChannelMessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class ChannelMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """A channel's history, posting, and staff moderation.

    List needs ``?channel=<id>``. Create runs ``PostToChannelAction``; destroy
    (``DeleteChannelMessageAction``) and ``ban/`` (``BanChannelAuthorAction``) are staff
    only. A refused action is 400 with its player-facing message as ``detail``.
    """

    serializer_class = ChannelMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChannelMessageFilterSet
    pagination_class = ChannelMessagePagination

    _STAFF_ACTIONS = frozenset({"destroy", "ban"})

    def get_permissions(self) -> list[BasePermission]:
        if self.action in self._STAFF_ACTIONS:
            return [IsAuthenticated(), IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[ChannelMessage]:
        return ChannelMessage.objects.select_related(
            "channel", "author_tenure__roster_entry__character_sheet__character"
        )

    def filter_queryset(self, queryset: QuerySet[ChannelMessage]) -> QuerySet[ChannelMessage]:
        # The required ?channel= filter is the list's; staff moderation finds a message
        # by id alone.
        if self.action != "list":
            return queryset
        return super().filter_queryset(queryset)

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if self.request is not None and self.request.user.is_authenticated:
            context["hidden_player_ids"] = hidden_author_player_ids(self.request.user)
        return context

    @extend_schema(
        request=ChannelMessageCreateSerializer,
        responses={201: ChannelMessageSerializer, 400: ChannelActionResultSerializer},
    )
    def create(self, request: Request) -> Response:
        """Post as the subscription's chosen identity (posting marks the channel read)."""
        payload = ChannelMessageCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = PostToChannelAction().run(
            actor=None,
            account=request.user,
            channel_id=payload.validated_data["channel"],
            body=payload.validated_data["body"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        message = self.get_queryset().get(pk=result.data["message_id"])
        return Response(self.get_serializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None, 400: ChannelActionResultSerializer})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Staff: delete a message from every reader's history."""
        message = self.get_object()
        result = DeleteChannelMessageAction().run(
            actor=None, account=request.user, message_id=message.pk
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=ChannelBanSerializer,
        responses={200: ChannelActionResultSerializer, 400: ChannelActionResultSerializer},
    )
    @action(detail=True, methods=["post"])
    def ban(self, request: Request, pk: str | None = None) -> Response:
        """Staff: ban this message's author from its channel."""
        message = self.get_object()
        payload = ChannelBanSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = BanChannelAuthorAction().run(
            actor=None,
            account=request.user,
            message_id=message.pk,
            reason=payload.validated_data["reason"],
        )
        response_status = status.HTTP_200_OK if result.success else status.HTTP_400_BAD_REQUEST
        return Response({"detail": result.message}, status=response_status)
