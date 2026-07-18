"""Inviter notification when an invitee submits an application (#2483).

Mirrors the shape of ``world.roster.services.mail_notifications.notify_mail_arrived``:
a best-effort websocket push via ``account.msg``. A notification failure must never
break application submission.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from evennia.utils.logger import log_trace

if TYPE_CHECKING:
    from world.character_creation.models import DraftApplication
    from world.roster.models import GameInvite

logger = logging.getLogger(__name__)


def notify_inviter_of_submission(invite: GameInvite, application: DraftApplication) -> None:
    """Push a websocket ping to the inviter when their invitee submits.

    Best-effort: a notification failure must never break submission (the
    DraftApplication is already committed by the time this runs).

    Args:
        invite: The claimed GameInvite linking inviter to invitee.
        application: The DraftApplication that was just submitted.
    """
    try:
        inviter_account = invite.inviter.account
        if inviter_account is None:
            return

        # Websocket ping — clients that care refetch the invite list
        inviter_account.msg(
            invitee_submitted=(
                (),
                {
                    "invite_id": invite.pk,
                    "character_name": (
                        application.draft.character_name
                        if application.draft
                        else application.character_name
                    ),
                },
            )
        )
    except Exception:  # noqa: BLE001 — best-effort notification; never break submission
        log_trace(f"invitee submission notification failed for invite={invite.pk}")
