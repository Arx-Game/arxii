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
from datetime import timedelta
import random
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from world.locations.constants import LocationParentType
from world.narrative.constants import AmbientTriggerType, GemitReach, NarrativeCategory
from world.narrative.models import (
    AmbientEmoteLine,
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

    puppet = session.puppet
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
        sheet = obj.character_sheet
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


def _eligible_ambient_lines(profile: object) -> list[AmbientEmoteLine]:
    """Most-specific-wins pool for ``profile``: room lines if any exist, else the area's.

    Mirrors the location-cascade convention (``LocationValueOverride``): a room-scoped
    pool entirely REPLACES an area-scoped one covering it, rather than merging with it.
    """
    select = (
        "trigger_species",
        "trigger_resonance",
        "trigger_distinction",
        "trigger_perceiving_society",
    )
    room_lines = list(
        AmbientEmoteLine.objects.filter(
            parent_type=LocationParentType.ROOM, room_profile=profile, is_active=True
        ).select_related(*select)
    )
    if room_lines:
        return room_lines
    if profile.area_id is None:
        return []
    return list(
        AmbientEmoteLine.objects.filter(
            parent_type=LocationParentType.AREA, area_id=profile.area_id, is_active=True
        ).select_related(*select)
    )


def _renown_min_matches(line: AmbientEmoteLine, persona: object) -> bool:
    """Mirrors the retired ``world.societies.fame_reactions._tier_meets`` (#881)."""
    from world.societies.constants import FAME_TIER_ORDER  # noqa: PLC0415

    offset = (
        (line.trigger_perceiving_society.fame_perception_offset or 0)
        if line.trigger_perceiving_society_id
        else 0
    )
    perceived_index = max(0, FAME_TIER_ORDER.index(persona.fame_tier) + offset)
    return perceived_index >= FAME_TIER_ORDER.index(line.trigger_min_fame_tier)


def _active_persona_or_none(character: object) -> object | None:
    """Mirrors the retired ``world.societies.fame_reactions._active_persona`` (#881)."""
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _trigger_matches(  # noqa: PLR0911 — one branch per trigger_type
    line: AmbientEmoteLine, character: object
) -> bool:
    """Does ``character`` meet ``line``'s trigger_type condition."""
    if line.trigger_type == AmbientTriggerType.NONE:
        return True
    if line.trigger_type == AmbientTriggerType.SPECIES:
        species = character.item_data.species
        return species is not None and species.pk == line.trigger_species_id
    if line.trigger_type == AmbientTriggerType.RESONANCE_MIN:
        # lifetime_earned, not balance — an identity marker ("how deeply attuned"),
        # not spendable currency that drains as the character spends it.
        return character.resonances.lifetime(line.trigger_resonance) >= line.trigger_minimum_value
    if line.trigger_type == AmbientTriggerType.DISTINCTION:
        from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

        return CharacterDistinction.objects.filter(
            character=character,
            distinction=line.trigger_distinction,
            secret__isnull=True,
        ).exists()
    if line.trigger_type == AmbientTriggerType.RENOWN_MIN:
        persona = _active_persona_or_none(character)
        if persona is None:
            return False
        return _renown_min_matches(line, persona)
    return False


def _deliver_ambient_line(line: AmbientEmoteLine, character: object, room: object) -> None:
    """Send the bystander line to the room (minus arriver) + the arriver line.

    Generalizes the retired ``world.societies.fame_reactions._deliver`` (#881).
    """
    category = (
        NarrativeCategory.RENOWN
        if line.trigger_type == AmbientTriggerType.RENOWN_MIN
        else NarrativeCategory.ATMOSPHERE
    )
    if line.bystander_body:
        bystander_sheets = []
        for obj in room.contents:
            if obj.pk == character.pk:
                continue
            sheet = obj.character_sheet
            if sheet is not None:
                bystander_sheets.append(sheet)
        if bystander_sheets:
            send_narrative_message(
                recipients=bystander_sheets,
                body=line.bystander_body,
                category=category,
                ooc_note="Ambient room reaction (bystander register, #2471).",
            )
    if line.arriver_body:
        arriver_sheet = character.character_sheet
        if arriver_sheet is not None:
            send_narrative_message(
                recipients=[arriver_sheet],
                body=line.arriver_body,
                category=category,
                ooc_note="Ambient room reaction (arriver register, #2471).",
            )


def emit_room_ambient_reaction(  # noqa: PLR0911 — one guard per quiet-exit case
    *, payload: object
) -> bool:
    """MOVED-triggered: fire at most one authored AmbientEmoteLine for the arriver (#2471).

    Generalizes the retired ``world.societies.fame_reactions.maybe_emit_fame_reaction``
    (#881) — species, resonance-threshold, distinction, and fame-tier conditions, plus
    plain unconditional atmosphere, through one mechanism. Called via the shared
    ``ambient_room_reaction`` Flow's CALL_SERVICE_FUNCTION step
    (``world.narrative.ambient_trigger_content.ensure_ambient_reaction_content``), with
    ``payload`` the ``flows.events.payloads.MovedPayload`` for the MOVED event.

    Returns True when a line fired (for tests); False on any quiet exit (no room
    profile, sheetless arriver, no eligible/matching line, cooldown active, or the
    fire_chance roll missed).
    """
    character = payload.character
    room = payload.destination
    if character is None or room is None:
        return False
    if character.character_sheet is None:
        return False
    profile = room.room_profile_or_none
    if profile is None:
        return False

    lines = _eligible_ambient_lines(profile)
    if not lines:
        return False

    matching = [line for line in lines if _trigger_matches(line, character)]
    if not matching:
        return False

    now = timezone.now()
    fireable = [
        line
        for line in matching
        if line.last_fired_at is None
        or now >= line.last_fired_at + timedelta(minutes=line.cooldown_minutes)
    ]
    if not fireable:
        return False

    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    line = select_weighted(fireable)
    if random.randint(1, 100) > line.fire_chance:  # noqa: S311
        return False

    _deliver_ambient_line(line, character, room)
    line.last_fired_at = now
    line.save(update_fields=["last_fired_at"])
    return True
