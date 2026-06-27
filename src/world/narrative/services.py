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

from world.narrative.constants import GemitReach, NarrativeCategory
from world.narrative.models import (
    AmbientStirLine,
    Gemit,
    NarrativeMessage,
    NarrativeMessageDelivery,
    UserCategoryMute,
    UserStoryMute,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.societies.models import Organization, Society
    from world.stories.models import BeatCompletion, EpisodeResolution, Era, Story


def send_narrative_message(  # noqa: PLR0913
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

    # Resolve muted accounts up front — one query each, not per-recipient.
    recipient_account_ids = [
        sheet.character.db_account_id
        for sheet in recipient_list
        if sheet.character.db_account_id is not None
    ]
    muted_account_ids: set[int] = set()
    if related_story is not None:
        muted_account_ids = set(
            UserStoryMute.objects.filter(
                story=related_story,
                account_id__in=recipient_account_ids,
            ).values_list("account_id", flat=True)
        )
    # Category-level mutes (e.g. a player squelching the WEATHER echo) — union with story mutes.
    if recipient_account_ids:
        muted_account_ids |= set(
            UserCategoryMute.objects.filter(
                category=category,
                account_id__in=recipient_account_ids,
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


def set_category_mute(*, account: AccountDB, category: str, muted: bool) -> None:
    """Mute or unmute a narrative category's real-time push for an account (#1522).

    Muting suppresses only the live ``character.msg()`` push — delivery rows are still created, so
    the messages stay readable in that category's tab.
    """
    if muted:
        UserCategoryMute.objects.get_or_create(account=account, category=category)
    else:
        UserCategoryMute.objects.filter(account=account, category=category).delete()


def is_category_muted(*, account: AccountDB, category: str) -> bool:
    """Whether an account has muted a narrative category's live push."""
    return UserCategoryMute.objects.filter(account=account, category=category).exists()


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


def _eligible_persona_ids(
    reach: str,
    societies: Iterable[Society],
    organizations: Iterable[Organization],
) -> set[int]:
    """Persona ids whose membership puts them in a SPECIFIED gemit's audience (#1450).

    The union of: members of any organization belonging to a target society, plus members of a
    target organization. (Society *reputation* alone — an outsider the society merely knows of —
    does not count; internal news goes to members.) Empty for GAME_WIDE.
    """
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if reach == GemitReach.GAME_WIDE:
        return set()
    eligible: set[int] = set()
    if societies:
        eligible.update(
            OrganizationMembership.objects.filter(organization__society__in=societies).values_list(
                "persona_id", flat=True
            )
        )
    if organizations:
        eligible.update(
            OrganizationMembership.objects.filter(organization__in=organizations).values_list(
                "persona_id", flat=True
            )
        )
    return eligible


def _session_in_audience(session: object, eligible_persona_ids: set[int]) -> bool:
    """Whether a connected session's active-persona character is in a scoped gemit's audience.

    Keyed on the *active* persona (the face the character is currently wearing) — a TEMPORARY mask
    holds no memberships, so a disguised character falls out of a SPECIFIED gemit's reach.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    puppet = getattr(session, "puppet", None)  # noqa: GETATTR_LITERAL
    if puppet is None:
        return False
    try:
        sheet = puppet.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return False
    return active_persona_for_sheet(sheet).id in eligible_persona_ids


def broadcast_gemit(  # noqa: PLR0913
    *,
    body: str,
    sender_account: AccountDB,
    reach: str = GemitReach.GAME_WIDE,
    societies: Iterable[Society] | None = None,
    organizations: Iterable[Organization] | None = None,
    related_era: Era | None = None,
    related_story: Story | None = None,
) -> Gemit:
    """Create a Gemit and push it to its ``reach`` audience in green (#1450).

    GAME_WIDE pushes to every connected session (the classic gemit). SPECIFIED pushes only to
    sessions whose active-persona character is a member of any target society or organization (the
    two combine freely); the targets are also recorded on the row so retroactive viewing stays
    scoped. The Gemit row persists either way; push failures are swallowed so a broadcast error
    never rolls back the record.
    """
    societies = list(societies or [])
    organizations = list(organizations or [])
    gemit = Gemit.objects.create(
        body=body,
        reach=reach,
        sender_account=sender_account,
        related_era=related_era,
        related_story=related_story,
    )
    if societies:
        gemit.reach_societies.set(societies)
    if organizations:
        gemit.reach_organizations.set(organizations)

    formatted = f"|G[GEMIT]|n {body}"
    eligible = _eligible_persona_ids(reach, societies, organizations)
    try:
        from evennia import SESSION_HANDLER  # noqa: PLC0415

        for session in SESSION_HANDLER.get_sessions():
            if reach != GemitReach.GAME_WIDE and not _session_in_audience(session, eligible):
                continue
            session.msg(text=(formatted, {}), type="gemit")
    except Exception as exc:  # noqa: BLE001 — best-effort broadcast; capture, don't propagate
        from world.player_submissions.services import report_error  # noqa: PLC0415

        report_error(exc, label="gemit_broadcast")
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


def emit_ambient_room_stir(room: ObjectDB, *, exclude: ObjectDB | None = None) -> None:
    """Send a source-ambiguous ambient line to a room's bystanders (#885).

    The audience half of the actor/audience split: the actor gets a clear
    STORY result; everyone else in the room gets a generic "something IC
    stirred here" line drawn from the staff-authored ``AmbientStirLine``
    pool. The pool is shared by design across emitting systems (missions
    today; GM events / room triggers / magic tomorrow) so observers cannot
    tell what stirred.

    Deliberately best-effort and quiet: an empty pool, an empty room, or a
    room of sheet-less objects emits nothing. ``exclude`` is the acting
    character (they already got the clear version).
    """
    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    lines = list(AmbientStirLine.objects.filter(is_active=True))
    if not lines:
        return
    recipients = []
    for obj in room.contents:
        if exclude is not None and obj.pk == exclude.pk:
            continue
        sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is not None:
            recipients.append(sheet)
    if not recipients:
        return
    line = select_weighted(lines)
    send_narrative_message(
        recipients=recipients,
        body=line.body,
        category=NarrativeCategory.HAPPENSTANCE,
        ooc_note="Ambient room stir (source withheld by design).",
    )
