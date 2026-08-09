"""TextChoices for the registration app."""

from django.db import models


class InviteStatus(models.TextChoices):
    """Derived (never stored) status of an ``AccountInvite`` — see its ``status`` property."""

    PENDING = "pending", "Pending"
    REDEEMED = "redeemed", "Redeemed"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


# Invites are redeemable for this long after issue, unless revoked first.
DEFAULT_INVITE_DURATION_DAYS = 30
