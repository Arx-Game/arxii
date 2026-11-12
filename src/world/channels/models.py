"""Models for player channels (#3299).

``Channel`` is a persistent named OOC channel: one curated PUBLIC channel, one ORG
channel per non-covert organization, plus optional STAFF channels. A message is
authored by a frozen ``RosterTenure`` (the identity the player chose to speak as);
account names are never stored on or shown with a message. ``ChannelSubscription``
holds a player's per-channel preferences, ``ChannelBan`` a staff ban.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.channels.constants import ChannelKind, ChannelNotificationLevel

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
ORGANIZATION_MODEL = "arxii.Organization"
ROSTER_TENURE_MODEL = "arxii.RosterTenure"
ACCOUNT_DB_MODEL = "accounts.AccountDB"


class Channel(SharedMemoryModel):
    """A persistent named OOC channel."""

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=16, choices=ChannelKind.choices)
    organization = models.OneToOneField(
        ORGANIZATION_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ooc_channel",
        help_text="ORG channel anchor: the organization whose members share this channel.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["kind", "name"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=ChannelKind.ORG, organization__isnull=False)
                    | (~models.Q(kind=ChannelKind.ORG) & models.Q(organization__isnull=True))
                ),
                name="channel_org_kind_iff_organization",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def display_name(self) -> str:
        """The name players see and type. An ORG channel reads its organization's name
        live, so an org rename never leaves a stale label; the stored ``name`` stays the
        unique slot (it may carry an " (org)" suffix from a provisioning clash)."""
        if self.kind == ChannelKind.ORG and self.organization is not None:
            return self.organization.name
        return self.name


class ChannelMessage(SharedMemoryModel):
    """One message on a channel, authored by the tenure the player spoke as."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    author_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.CASCADE,
        related_name="channel_messages",
        help_text="The tenure spoken as, frozen at post time.",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["created_at", "pk"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["channel", "created_at"], name="channel_msg_chan_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Message #{self.pk} on {self.channel_id}"


class ChannelSubscription(SharedMemoryModel):
    """An account's membership in a channel and its per-channel preferences."""

    account = models.ForeignKey(
        ACCOUNT_DB_MODEL, on_delete=models.CASCADE, related_name="channel_subscriptions"
    )
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="subscriptions")
    display_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The tenure this account speaks as in this channel.",
    )
    muted = models.BooleanField(default=False)
    collapsed = models.BooleanField(default=False)
    notification_level = models.CharField(
        max_length=8,
        choices=ChannelNotificationLevel.choices,
        default=ChannelNotificationLevel.BADGE,
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    last_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "channel__name"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["account", "channel"], name="unique_channel_subscription"
            ),
        ]

    def __str__(self) -> str:
        return f"Subscription of account {self.account_id} to channel {self.channel_id}"


class ChannelBan(SharedMemoryModel):
    """A staff ban of an account from a channel."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="bans")
    account = models.ForeignKey(
        ACCOUNT_DB_MODEL, on_delete=models.CASCADE, related_name="channel_bans"
    )
    banned_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["channel", "account"], name="unique_channel_ban"),
        ]

    def __str__(self) -> str:
        return f"Ban of account {self.account_id} from channel {self.channel_id}"
