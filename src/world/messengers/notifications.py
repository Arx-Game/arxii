"""Arrival notice for missives (#3289).

Mirrors ``world.roster.services.mail_notifications.notify_mail_arrived``: a slim
websocket ping (clients refetch the list on receipt), plus a plain-text twin
for telnet sessions only so a browser never shows it twice.

Anonymity boundary: the notice names the persona the letter was addressed to and the sender
as this recipient sees them (``display.shown_name``, the one rule every missive surface uses).
It never carries a character, tenure or account of the sender. It goes to the recipient
persona's character only.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from web.webclient.message_types import MissiveArrivedPayload
from world.messengers.display import shown_name
from world.scenes.interaction_services import send_text_to_non_web

if TYPE_CHECKING:
    from world.messengers.models import Missive


def notify_missive_arrived(missive: Missive) -> None:
    """Tell the recipient persona's character that a missive has arrived.

    Best-effort by its caller: ``deliver_due_missives`` registers this with
    ``transaction.on_commit(..., robust=True)``, so a failure is logged and never undoes the
    delivery stamp or stops the next push. A character nobody is playing receives nothing
    (``msg`` to no sessions is a no-op); the unread count carries it.
    """
    recipient = missive.recipient_persona
    sheet = recipient.character_sheet
    character = sheet.character
    if character is None:
        return
    sender_display = shown_name(missive.sender_persona, sheet)
    payload = asdict(
        MissiveArrivedPayload(
            missive_id=missive.pk,
            recipient_persona_name=recipient.name,
            sender_display=sender_display,
        )
    )
    character.msg(missive_arrived=((), payload))
    send_text_to_non_web(
        character,
        f"{_with_article(missive.method.name.lower())} brings you a missive for "
        f"{recipient.name} from {sender_display}. (missive/read {missive.pk})",
    )


def _with_article(noun: str) -> str:
    """'A courier', 'An owl': the article by the noun's first letter."""
    article = "An" if noun[:1] in _VOWELS and noun else "A"
    return f"{article} {noun}"


_VOWELS = frozenset("aeiou")
