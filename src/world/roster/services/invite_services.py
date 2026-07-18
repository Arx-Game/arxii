"""Service functions for game invites (#2483).

These functions use the ``game_invite`` prefix to avoid collision with
``world.gm/services.py``'s ``create_invite``/``claim_invite``/``revoke_invite``
(which operate on ``GMRosterInvite``, a different domain).
"""

from __future__ import annotations

from datetime import timedelta
import logging
import secrets
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.roster.models import GameInvite, InviteStatus

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import PlayerData
    from world.character_creation.models import DraftApplication

logger = logging.getLogger(__name__)

DEFAULT_INVITE_EXPIRY_DAYS = 30


def _inviter_meets_trust_threshold(inviter: PlayerData) -> bool:
    """Check if the inviter has sufficient trust to send invites.

    Uses the 'INVITE' TrustCategory with a BASIC minimum threshold.
    Returns True if the inviter meets the threshold, False otherwise.
    """
    from world.stories.models import PlayerTrust  # noqa: PLC0415
    from world.stories.types import TrustLevel  # noqa: PLC0415

    try:
        trust = PlayerTrust.objects.get(account=inviter.account)
    except PlayerTrust.DoesNotExist:
        return False

    return trust.has_minimum_trust_for_categories(
        [{"category": "INVITE", "minimum_level": TrustLevel.BASIC}]
    )


@transaction.atomic
def create_game_invite(
    inviter: PlayerData,
    message: str,
    expires_in_days: int | None = None,
) -> GameInvite:
    """Create a contextual game invite.

    Validates that the inviter meets the trust threshold before creating.

    Args:
        inviter: The PlayerData of the trusted player sending the invite.
        message: The contextual note the friend will see on registration.
        expires_in_days: Optional expiry window. None = no expiry.

    Returns:
        The created GameInvite instance.

    Raises:
        PermissionError: If the inviter does not meet the trust threshold.
    """
    if not _inviter_meets_trust_threshold(inviter):
        msg = "Inviter does not meet the trust threshold to send invites."
        raise PermissionError(msg)

    expires_at = None
    if expires_in_days is not None:
        expires_at = timezone.now() + timedelta(days=expires_in_days)

    return GameInvite.objects.create(
        inviter=inviter,
        token=secrets.token_urlsafe(48),
        message=message,
        status=InviteStatus.PENDING,
        expires_at=expires_at,
    )


def resolve_invite(token: str) -> GameInvite | None:
    """Resolve a token to its invite for registration-page context display.

    Returns the invite if it's pending and not expired. Returns None for
    claimed, revoked, expired, or nonexistent tokens. This is safe to expose
    to unauthenticated users — it only returns display-safe context.
    """
    try:
        invite = GameInvite.objects.get(token=token)
    except GameInvite.DoesNotExist:
        return None

    if invite.status != InviteStatus.PENDING:
        return None

    if invite.expires_at is not None and timezone.now() >= invite.expires_at:
        return None

    return invite


@transaction.atomic
def claim_game_invite(token: str, account: AccountDB) -> GameInvite:
    """Link an invite to a newly-registered account (first login).

    Args:
        token: The invite token from the registration URL.
        account: The newly-registered account claiming the invite.

    Returns:
        The claimed GameInvite instance.

    Raises:
        ValueError: If the token is invalid, already claimed, revoked, or expired.
    """
    try:
        invite = GameInvite.objects.get(token=token)
    except GameInvite.DoesNotExist:
        msg = "Invalid invite token."
        raise ValueError(msg) from None

    if invite.status == InviteStatus.CLAIMED:
        msg = "This invite has already been claimed."
        raise ValueError(msg)

    if invite.status == InviteStatus.REVOKED:
        msg = "This invite has been revoked."
        raise ValueError(msg)

    if invite.expires_at is not None and timezone.now() >= invite.expires_at:
        invite.status = InviteStatus.EXPIRED
        invite.save(update_fields=["status"])
        msg = "This invite has expired."
        raise ValueError(msg)

    invite.status = InviteStatus.CLAIMED
    invite.invited_account = account
    invite.claimed_at = timezone.now()
    invite.save(update_fields=["status", "invited_account", "claimed_at"])
    return invite


@transaction.atomic
def revoke_game_invite(invite: GameInvite, revoked_by: AccountDB) -> None:
    """Revoke an invite.

    Args:
        invite: The GameInvite to revoke.
        revoked_by: The account revoking the invite (inviter or staff).
    """
    invite.status = InviteStatus.REVOKED
    invite.revoked_at = timezone.now()
    invite.revoked_by = revoked_by
    invite.save(update_fields=["status", "revoked_at", "revoked_by"])


def get_invite_for_account(account: AccountDB) -> GameInvite | None:
    """Get the claimed invite for an account, if one exists.

    Used by ``annotate_application()`` to find the invite context when a
    DraftApplication is submitted.

    Args:
        account: The account to look up.

    Returns:
        The claimed GameInvite for this account, or None.
    """
    return GameInvite.objects.filter(
        invited_account=account,
        status=InviteStatus.CLAIMED,
    ).first()


def annotate_application(application: DraftApplication, account: AccountDB) -> GameInvite | None:
    """Attach invite context to a DraftApplication (sets invited_via FK).

    Returns the linked GameInvite if one exists, None if the account has no
    claimed invite (no-op in that case).

    Args:
        application: The DraftApplication to annotate.
        account: The submitting account.

    Returns:
        The linked GameInvite, or None.
    """
    invite = get_invite_for_account(account)
    if invite is None:
        return None

    application.invited_via = invite
    application.save(update_fields=["invited_via"])
    return invite
