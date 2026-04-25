"""Services for creating and delivering narrative messages.

send_narrative_message is the single creation entry point. It creates a
NarrativeMessage plus one NarrativeMessageDelivery per recipient inside
one transaction, then pushes the message to any puppeted recipient's
session. Offline recipients keep their delivery queued (delivered_at=None)
for login catch-up via deliver_queued_messages.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import BeatCompletion, EpisodeResolution, Story


def send_narrative_message(  # noqa: PLR0913 — all context FKs are independent and kwarg-only
    *,
    recipients: Iterable[CharacterSheet],
    body: str,
    category: str,
    sender_account: AccountDB | None = None,
    ooc_note: str = "",
    related_story: Story | None = None,
    related_beat_completion: BeatCompletion | None = None,
    related_episode_resolution: EpisodeResolution | None = None,
) -> NarrativeMessage:
    """Create a NarrativeMessage and fan out deliveries to each recipient.

    Real-time push to puppeted recipients via character.msg(); deliveries
    to offline recipients stay unmarked (delivered_at=None) until the
    recipient's next login triggers catch-up delivery.

    Returns the NarrativeMessage instance.
    """
    recipient_list = list(recipients)
    with transaction.atomic():
        msg = NarrativeMessage.objects.create(
            body=body,
            ooc_note=ooc_note,
            category=category,
            sender_account=sender_account,
            related_story=related_story,
            related_beat_completion=related_beat_completion,
            related_episode_resolution=related_episode_resolution,
        )
        deliveries = [
            NarrativeMessageDelivery(message=msg, recipient_character_sheet=sheet)
            for sheet in recipient_list
        ]
        NarrativeMessageDelivery.objects.bulk_create(deliveries)

    # Online push — after commit so any listener sees consistent state.
    queryset = NarrativeMessageDelivery.objects.filter(message=msg).select_related(
        "recipient_character_sheet__character",
    )
    for delivery in queryset:
        _push_to_online_recipient(delivery)

    return msg


def deliver_queued_messages(character_sheet: CharacterSheet) -> int:
    """Push all undelivered messages for this character and mark delivered.

    Called at character login via the stories login hook. Returns the
    count of deliveries that were pushed (or attempted). Deliveries whose
    session push still fails (character not actually puppeted) remain
    queued for the next attempt.
    """
    queued = NarrativeMessageDelivery.objects.filter(
        recipient_character_sheet=character_sheet,
        delivered_at__isnull=True,
    ).select_related("message", "recipient_character_sheet__character")

    count = 0
    for delivery in queued:
        _push_to_online_recipient(delivery)
        count += 1
    return count


def _push_to_online_recipient(delivery: NarrativeMessageDelivery) -> None:
    """Push the message to the recipient's puppeted session if online.

    Marks delivered_at=now when the push succeeds. If the character isn't
    currently puppeted, leaves the delivery queued for login catch-up.
    """
    character = delivery.recipient_character_sheet.character
    sessions = list(character.sessions.all())
    if not sessions:
        return  # offline; leave for catch-up
    formatted = _format_message_for_display(delivery.message)
    character.msg(formatted, type="narrative")
    delivery.delivered_at = timezone.now()
    delivery.save(update_fields=["delivered_at"])


def _format_message_for_display(message: NarrativeMessage) -> str:
    """Format a message for in-text display in a connected session.

    Adds a distinct color tag so clients can style it apart from normal
    messages. The frontend roadmap calls for light red for narrative
    messages — Evennia color code |R.

    The OOC note is NOT included in the player-facing text; it's visible
    only through the staff/GM admin and API surfaces.
    """
    return f"|R[NARRATIVE]|n {message.body}"
