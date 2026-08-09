"""Service functions for invitation-gated account registration (#3054).

Mutations go through this module, never direct model writes from views or
the adapter — mirrors the project's action/service-function convention.
"""

from datetime import timedelta
import secrets

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.registration.constants import DEFAULT_INVITE_DURATION_DAYS
from world.registration.models import AccountInvite

TOKEN_BYTES = 32


def issue_invite(email: str, invited_by: AccountDB, note: str = "") -> AccountInvite:
    """Issue an invite for ``email``.

    An already-active (redeemable) invite for the same email is returned
    unchanged rather than duplicated (active-invite dedup); an email with
    only dead invites (redeemed/revoked/expired) gets a fresh row.
    """
    normalized_email = email.strip().lower()
    existing = (
        AccountInvite.objects.filter(
            email__iexact=normalized_email,
            redeemed_at__isnull=True,
            revoked_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None and not existing.is_expired:
        return existing

    return AccountInvite.objects.create(
        email=normalized_email,
        token=secrets.token_urlsafe(TOKEN_BYTES),
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=DEFAULT_INVITE_DURATION_DAYS),
        note=note,
    )


@transaction.atomic
def revoke_invite(invite: AccountInvite, by: AccountDB) -> AccountInvite:  # noqa: ARG001
    """Revoke an un-redeemed invite. ``by`` is accepted for future audit-log use."""
    invite.revoked_at = timezone.now()
    invite.save(update_fields=["revoked_at"])
    return invite


def signup_allowed(email: str, token: str) -> bool:
    """True when ``token`` is a currently-redeemable invite bound to ``email``.

    Never distinguishes *why* a token fails (no invite / wrong email /
    expired / revoked / already redeemed) — the adapter surfaces one neutral
    rejection for all of them (leak-analysis: no oracle for probing which
    emails hold invites).
    """
    if not email or not token:
        return False
    normalized_email = email.strip().lower()
    try:
        invite = AccountInvite.objects.get(token=token)
    except AccountInvite.DoesNotExist:
        return False
    return invite.email.lower() == normalized_email and invite.is_redeemable


@transaction.atomic
def redeem_invite(token: str, email: str, account: AccountDB) -> AccountInvite | None:
    """Validate + stamp redemption for the invite backing this signup.

    Returns the redeemed invite, or ``None`` if ``token``/``email`` no
    longer describe a redeemable invite (already redeemed by a concurrent
    request, expired, revoked, or mismatched) — called from
    ``ArxAccountAdapter.save_user`` immediately after account creation, so a
    ``None`` here just means no invite gets stamped (the signup itself
    already happened, gated separately by ``is_open_for_signup``).
    """
    if not token:
        return None
    normalized_email = (email or "").strip().lower()
    try:
        invite = AccountInvite.objects.select_for_update().get(token=token)
    except AccountInvite.DoesNotExist:
        return None
    if invite.email.lower() != normalized_email or not invite.is_redeemable:
        return None
    invite.redeemed_at = timezone.now()
    invite.redeemed_by = account
    invite.save(update_fields=["redeemed_at", "redeemed_by"])
    return invite
