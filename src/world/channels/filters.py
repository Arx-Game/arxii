"""Filters for the player channels API (#3299)."""

from __future__ import annotations

from django.db.models import QuerySet
import django_filters

from world.channels.constants import ChannelKind
from world.channels.models import Channel, ChannelMessage, ChannelSubscription
from world.channels.services import accessible_channels_for, history_for


class ChannelFilterSet(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(choices=ChannelKind.choices)

    class Meta:
        model = Channel
        fields = ["kind"]


class ChannelSubscriptionFilterSet(django_filters.FilterSet):
    channel = django_filters.NumberFilter(field_name="channel_id")

    class Meta:
        model = ChannelSubscription
        fields = ["channel"]


class ChannelMessageFilterSet(django_filters.FilterSet):
    """``?channel=<id>`` is required (400 without it). A channel the requester cannot
    reach lists nothing, the same as one that does not exist."""

    channel = django_filters.NumberFilter(method="filter_channel", required=True)

    class Meta:
        model = ChannelMessage
        fields = ["channel"]

    def filter_channel(
        self, queryset: QuerySet[ChannelMessage], name: str, value: int
    ) -> QuerySet[ChannelMessage]:
        account = self.request.user
        channel = accessible_channels_for(account).filter(pk=value).first()
        if channel is None:
            return queryset.none()
        # Newest first: the client pages backwards from the latest message.
        return history_for(account, channel).order_by("-created_at", "-pk")
