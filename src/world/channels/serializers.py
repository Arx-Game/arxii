"""DRF serializers for the player channels API (#3299).

Anonymity: nothing here serializes an account, an account name, an author tenure id,
or any other account's tenures. A message names its author only by the frozen
tenure's ``speaker_name``; the identity picker lists the requester's own tenures.

Serializer context (set by the views, ADR-0260: request data travels as an explicit
argument): ``subscriptions`` (channel pk -> the requester's subscription),
``unread_counts`` (subscription pk -> count), ``hidden_player_ids`` (authors whose rows
this reader sees hidden).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.channels.models import Channel, ChannelMessage, ChannelSubscription
from world.channels.services import (
    UNSET,
    eligible_tenures,
    findable_channels_for,
    subscribe,
    unread_count,
    update_subscription,
)
from world.channels.types import ChannelError
from world.roster.models import RosterTenure


class _FindableChannelField(serializers.PrimaryKeyRelatedField):
    """A channel id the requester may name (``findable_channels_for``). An org channel
    the requester can neither reach nor is banned from is DRF's "invalid pk", the same as
    a missing one, so the API never confirms an org channel to a non-member."""

    def get_queryset(self) -> Any:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return Channel.objects.none()
        return findable_channels_for(request.user)


class _OwnCurrentTenureField(serializers.PrimaryKeyRelatedField):
    """A tenure id the requester holds right now. Any other id (another account's, an
    ended one, a missing one) is the same "invalid pk" refusal, so the field never
    confirms that someone else's tenure exists."""

    def get_queryset(self) -> Any:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return RosterTenure.objects.none()
        return RosterTenure.objects.current().filter(player_data_id=request.user.pk)


class ChannelSubscriptionSerializer(serializers.ModelSerializer):
    """The requester's own subscription row and its preferences.

    ``channel`` is set on create only. ``display_tenure`` must be one of the requester's
    tenures eligible for the channel (an alt outside the org is refused with 400).
    """

    channel = _FindableChannelField(queryset=Channel.objects.none())
    display_tenure = _OwnCurrentTenureField(
        queryset=RosterTenure.objects.none(), allow_null=True, required=False
    )
    display_label = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChannelSubscription
        fields = [
            "id",
            "channel",
            "display_tenure",
            "display_label",
            "muted",
            "collapsed",
            "notification_level",
            "sort_order",
            "unread_count",
        ]
        read_only_fields = ["id"]

    def get_display_label(self, obj: ChannelSubscription) -> str | None:
        """Who the requester speaks as here (the speaker name), or null if unchosen."""
        tenure = obj.display_tenure
        return tenure.speaker_name if tenure is not None else None

    def get_unread_count(self, obj: ChannelSubscription) -> int:
        """Unread messages; 0 for a muted channel or notification level "none"."""
        counts = self.context.get("unread_counts") or {}
        if obj.pk in counts:
            return counts[obj.pk]
        return unread_count(obj)

    def validate_channel(self, value: Channel) -> Channel:
        if self.instance is not None and value.pk != self.instance.channel_id:
            msg = "A subscription's channel can't be changed."
            raise serializers.ValidationError(msg)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        tenure = attrs.get("display_tenure")
        if tenure is not None:
            channel = attrs.get("channel") or self.instance.channel
            account = self.context["request"].user
            if tenure.pk not in {t.pk for t in eligible_tenures(account, channel)}:
                raise serializers.ValidationError(
                    {"display_tenure": ChannelError.INELIGIBLE_IDENTITY}
                )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> ChannelSubscription:
        account = self.context["request"].user
        channel = validated_data.pop("channel")
        with transaction.atomic():
            try:
                subscription = subscribe(account, channel)
            except ChannelError as exc:
                raise serializers.ValidationError({"channel": exc.user_message}) from exc
            return self._apply_preferences(subscription, validated_data)

    def update(
        self, instance: ChannelSubscription, validated_data: dict[str, Any]
    ) -> ChannelSubscription:
        validated_data.pop("channel", None)
        with transaction.atomic():
            return self._apply_preferences(instance, validated_data)

    @staticmethod
    def _apply_preferences(
        subscription: ChannelSubscription, data: dict[str, Any]
    ) -> ChannelSubscription:
        # validate() already checked the identity; this catches the race where the
        # tenure lost eligibility in between (the service re-checks it).
        try:
            return update_subscription(
                subscription,
                display_tenure=data.get("display_tenure", UNSET),
                muted=data.get("muted", UNSET),
                collapsed=data.get("collapsed", UNSET),
                notification_level=data.get("notification_level", UNSET),
                sort_order=data.get("sort_order", UNSET),
            )
        except ChannelError as exc:
            raise serializers.ValidationError({"display_tenure": exc.user_message}) from exc


class ChannelSerializer(serializers.ModelSerializer):
    """A channel the requester can reach, with their own subscription (or null)."""

    name = serializers.CharField(source="display_name", read_only=True)
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        fields = ["id", "name", "description", "kind", "subscription"]
        read_only_fields = fields

    @extend_schema_field(ChannelSubscriptionSerializer(allow_null=True))
    def get_subscription(self, obj: Channel) -> dict[str, Any] | None:
        subscription = (self.context.get("subscriptions") or {}).get(obj.pk)
        if subscription is None:
            return None
        return ChannelSubscriptionSerializer(subscription, context=self.context).data


class ChannelIdentitySerializer(serializers.Serializer):
    """One of the requester's own tenures eligible to speak in a channel."""

    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(source="speaker_name", read_only=True)


class ChannelMessageSerializer(serializers.ModelSerializer):
    """A channel message as this reader sees it. A blocked author's row comes back with
    ``is_hidden`` true and an empty speaker and body (the client shows "N hidden")."""

    speaker = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    is_hidden = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()

    class Meta:
        model = ChannelMessage
        fields = ["id", "channel", "speaker", "body", "is_hidden", "is_own", "created_at"]
        read_only_fields = fields

    def get_is_hidden(self, obj: ChannelMessage) -> bool:
        """Whether this reader and the author block each other."""
        hidden = self.context.get("hidden_player_ids") or set()
        return obj.author_tenure.player_data_id in hidden

    def get_speaker(self, obj: ChannelMessage) -> str:
        """The author's speaker name ("Ariel" or "2nd player of Ariel"); empty if hidden."""
        return "" if self.get_is_hidden(obj) else obj.author_tenure.speaker_name

    def get_body(self, obj: ChannelMessage) -> str:
        """The message text; empty if hidden."""
        return "" if self.get_is_hidden(obj) else obj.body

    def get_is_own(self, obj: ChannelMessage) -> bool:
        """Whether the requester wrote it (under any of their tenures)."""
        request = self.context.get("request")
        return request is not None and obj.author_tenure.player_data_id == request.user.pk


class ChannelMessageCreateSerializer(serializers.Serializer):
    """Post input. Emptiness, length, access and identity are refused by the post
    action with the player-facing reason (400)."""

    channel = serializers.IntegerField()
    body = serializers.CharField(allow_blank=True, trim_whitespace=False)


class ChannelBanSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class ChannelActionResultSerializer(serializers.Serializer):
    detail = serializers.CharField()
