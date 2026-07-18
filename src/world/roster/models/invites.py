"""GameInvite model for player-to-friend contextual invites (#2483)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class InviteStatus(models.TextChoices):
    """Status choices for game invites."""

    PENDING = "pending", "Pending"
    CLAIMED = "claimed", "Claimed"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"


class GameInvite(SharedMemoryModel):
    """A contextual invite from a trusted player to a friend.

    Created by an inviter with a message/purpose. The friend registers via
    a URL carrying the invite token, which survives the allauth email-verification
    gap (stored client-side). On first login, the token is claimed and linked
    to the new account. The invite's context annotates the invitee's first
    DraftApplication, and the inviter is notified on submission.
    """

    inviter = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="sent_invites",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="URL-safe random token (secrets.token_urlsafe(48))",
    )
    message = models.TextField(
        help_text="The inviter's contextual note to the friend (why they're invited).",
    )
    status = models.CharField(
        max_length=10,
        choices=InviteStatus.choices,
        default=InviteStatus.PENDING,
    )
    invited_account = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="received_invites",
        help_text="Set when the invitee claims the token (first login).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional expiry; null = no expiry.",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_invites",
        help_text="Account that revoked this invite (inviter or staff).",
    )

    @property
    def is_usable(self) -> bool:
        """True if this invite can still be claimed."""
        return self.status == InviteStatus.PENDING

    def __str__(self) -> str:
        return f"GameInvite({self.token[:8]}… → {self.status})"

    class Meta:
        verbose_name = "Game Invite"
        verbose_name_plural = "Game Invites"
        ordering = ["-created_at"]
