"""Models for invitation-gated account registration (#3054).

``RegistrationConfig`` is the DB-singleton open/closed toggle (mirrors
``world.scenes.models.SceneRoundDefaultsConfig`` — staff flip it via admin,
no deploy). ``AccountInvite`` is a staff-issued, per-email single-use
invitation; see ``world.registration.services`` for the mutation surface
(issue/revoke/redeem) and ``evennia_extensions.adapters.ArxAccountAdapter``
for where the gate is enforced.
"""

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.registration.constants import InviteStatus

# Lazy model reference (Django app_label.ModelName), extracted to satisfy S1192.
ACCOUNT_DB_MODEL = "accounts.AccountDB"


class RegistrationConfig(SharedMemoryModel):
    """Singleton (pk=1) staff-tunable toggle for open account registration."""

    objects = ArxSharedMemoryManager()

    registration_open = models.BooleanField(
        default=False,
        help_text="When True, anyone can self-register; no invite required.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registration_config_updates",
    )

    class Meta:
        verbose_name = "Registration Config"
        verbose_name_plural = "Registration Config"

    def __str__(self) -> str:
        state = "open" if self.registration_open else "closed"
        return f"RegistrationConfig(pk={self.pk}, {state})"


def get_registration_config() -> RegistrationConfig:
    """Return the singleton row, creating it (closed by default) on first use."""
    obj = RegistrationConfig.objects.cached_singleton()
    if obj is None:
        obj, _ = RegistrationConfig.objects.get_or_create(pk=1)
    return obj


class AccountInvite(SharedMemoryModel):
    """A staff-issued, per-email single-use invitation to register an account.

    Email-bound (not a bare redeemable code) so an issued invite is
    auditable — "who let this person in" — and can't be shared beyond the
    invited address. Expiry is a plain column checked at signup time, not a
    scheduled sweep — an expired row simply stops being redeemable.
    """

    email = models.EmailField(db_index=True)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_account_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(help_text="Invite cannot be redeemed after this time.")
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Why this person was invited (staff-only, never shown to the invitee).",
    )

    class Meta:
        verbose_name = "Account Invite"
        verbose_name_plural = "Account Invites"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AccountInvite({self.email}, {self.status})"

    @property
    def is_redeemed(self) -> bool:
        return self.redeemed_at is not None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_redeemable(self) -> bool:
        """True when this invite can still be used to satisfy the signup gate."""
        return not self.is_redeemed and not self.is_revoked and not self.is_expired

    @property
    def status(self) -> str:
        """Derived state for staff display — never stored, always computed."""
        if self.is_revoked:
            return InviteStatus.REVOKED
        if self.is_redeemed:
            return InviteStatus.REDEEMED
        if self.is_expired:
            return InviteStatus.EXPIRED
        return InviteStatus.PENDING
