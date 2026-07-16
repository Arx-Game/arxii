"""Arrival notification for ``PlayerMail`` (#2160).

The web-first mail surface needs a live nudge when new mail lands instead of requiring a
poll/refresh — the ``mail_arrived`` websocket push fills that gap, mirroring
``world.battles.services.notify_battle_state_changed``'s slim-ping shape (clients that care
refetch the REST list on receipt) and
``world.scenes.friend_services.notify_friends_of_status``'s tenure->account traversal.

Anonymity boundary: the payload is tenure-display-only. It must never carry an account id,
username, or anything else that would let a recipient unmask the sender's real player.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from evennia.utils.logger import log_trace

from web.webclient.message_types import MailArrivedPayload

if TYPE_CHECKING:
    from world.roster.models import PlayerMail, RosterTenure


def notify_mail_arrived(recipient_tenure: RosterTenure, mail: PlayerMail) -> None:
    """Push a ``mail_arrived`` ping to the recipient's account.

    Best-effort: a notification failure must never break mail delivery (the mail row is already
    committed by the time this runs -- see ``PlayerMailViewSet.perform_create``'s
    ``transaction.on_commit`` wrapper). ``account.msg`` to an offline account is a harmless
    no-op, so an offline recipient simply doesn't see it.
    """
    try:
        account = recipient_tenure.player_data.account
        if account is None:
            return
        sender_tenure = mail.sender_tenure
        sender_display = sender_tenure.display_name if sender_tenure is not None else "Unknown"
        payload = asdict(
            MailArrivedPayload(
                mail_id=mail.pk,
                sender_display=sender_display,
                subject=mail.subject,
            )
        )
        account.msg(mail_arrived=((), payload))
    except Exception:  # noqa: BLE001 — best-effort arrival ping; never break mail send (#2160)
        log_trace(f"mail arrival ping failed for mail={mail.pk}")
