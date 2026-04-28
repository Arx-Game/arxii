"""Services for creating and delivering narrative messages.

send_narrative_message is the single creation entry point. It creates a
NarrativeMessage plus one NarrativeMessageDelivery per recipient inside
one transaction, then pushes the message to any puppeted recipient's
session. Offline recipients keep their delivery queued (delivered_at=None)
for login catch-up via deliver_queued_messages.

send_story_ooc_message fans out an OOC notice from a Lead GM or staff to
all scope-appropriate participants of a story.

broadcast_gemit pushes a staff-authored server-wide broadcast to all
online sessions and persists a Gemit record for retroactive viewing.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.narrative.models import Gemit, NarrativeMessage, NarrativeMessageDelivery, UserStoryMute

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import BeatCompletion, EpisodeResolution, Era, Story


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

    When related_story is set, recipients whose account has a UserStoryMute
    for that story are skipped for the real-time push. Their delivery rows
    are still created so login catch-up surfaces missed updates.

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

    # Resolve muted accounts up front — one query, not per-recipient.
    muted_account_ids: set[int] = set()
    if related_story is not None:
        muted_account_ids = set(
            UserStoryMute.objects.filter(
                story=related_story,
                account__in=[
                    sheet.character.db_account_id
                    for sheet in recipient_list
                    if sheet.character.db_account_id is not None
                ],
            ).values_list("account_id", flat=True)
        )

    # Online push — after commit so any listener sees consistent state.
    queryset = NarrativeMessageDelivery.objects.filter(message=msg).select_related(
        "recipient_character_sheet__character",
    )
    for delivery in queryset:
        account_id = delivery.recipient_character_sheet.character.db_account_id
        if account_id in muted_account_ids:
            continue  # muted: delivery row exists; skip real-time push
        _push_to_online_recipient(delivery)

    return msg


def send_story_ooc_message(
    *,
    story: Story,
    sender_account: AccountDB,
    body: str,
    ooc_note: str = "",
) -> NarrativeMessage:
    """Lead GM or staff sends an OOC notice to all participants of a story.

    Resolves participants by scope (CHARACTER / GROUP / GLOBAL) and fans out
    NarrativeMessageDelivery rows with category=STORY. Service receives
    pre-validated inputs (permission gating in view; body length in serializer).
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

    recipients = list(_resolve_story_participants(story))
    return send_narrative_message(
        recipients=recipients,
        body=body,
        category=NarrativeCategory.STORY,
        sender_account=sender_account,
        ooc_note=ooc_note,
        related_story=story,
    )


def broadcast_gemit(
    *,
    body: str,
    sender_account: AccountDB,
    related_era: Era | None = None,
    related_story: Story | None = None,
) -> Gemit:
    """Create a Gemit and push to all currently-connected sessions in green.

    The Gemit row persists for retroactive viewing. The real-time push uses
    evennia.SESSION_HANDLER to reach all connected sessions; push failures
    are swallowed so that broadcast errors do not roll back the record.
    """
    gemit = Gemit.objects.create(
        body=body,
        sender_account=sender_account,
        related_era=related_era,
        related_story=related_story,
    )
    formatted = f"|G[GEMIT]|n {body}"
    try:
        from evennia import SESSION_HANDLER  # noqa: PLC0415

        for session in SESSION_HANDLER.get_sessions():
            session.msg(text=(formatted, {}), type="gemit")
    except Exception:  # noqa: BLE001, S110 — broadcast failure must not raise; record already saved
        pass
    return gemit


def _resolve_story_participants(story: Story) -> Generator[CharacterSheet]:
    """Yield CharacterSheet for every active participant of the story.

    CHARACTER scope: the story's owning character_sheet (via story.character_sheet).
    GROUP scope: active GMTableMembership personas' character_sheets for
                 story.primary_table.
    GLOBAL scope: active StoryParticipation members' character sheets.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.stories.constants import StoryScope  # noqa: PLC0415

    match story.scope:
        case StoryScope.CHARACTER:
            if story.character_sheet_id is not None:
                yield story.character_sheet
        case StoryScope.GROUP:
            if story.primary_table_id is not None:
                memberships = story.primary_table.memberships.filter(
                    left_at__isnull=True
                ).select_related("persona__character_sheet")
                for membership in memberships:
                    persona = membership.persona
                    if persona.character_sheet_id is not None:
                        yield persona.character_sheet
        case StoryScope.GLOBAL:
            participations = story.participants.filter(is_active=True).select_related(
                "character",
            )
            for participation in participations:
                try:
                    yield participation.character.sheet_data
                except CharacterSheet.DoesNotExist:
                    continue


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
