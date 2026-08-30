"""Service functions for event lifecycle, invitations, and visibility."""

from datetime import datetime, timedelta
import math
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from evennia_extensions.models import ObjectDisplayData
from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import (
    CateringRole,
    Event,
    EventCatering,
    EventGrandeurContribution,
    EventHost,
    EventInvitation,
    EventModification,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.currency.models import CharacterPurse, OrganizationTreasury
    from world.items.models import ItemInstance
from world.events.types import EventError
from world.game_clock.constants import TimePhase
from world.game_clock.models import GameClock
from world.progression.services.scene_rewards import on_scene_finished
from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import Persona, Scene
from world.societies.models import Organization, Society

# Minimum gap between events at the same location (real hours)
LOCATION_GAP_HOURS = 6


def derive_ic_time_from_real(real_time: datetime) -> datetime | None:
    """Derive an IC datetime from a real datetime using the game clock.

    Returns None if no game clock is configured.
    """
    clock = GameClock.get_active()
    if clock is None or clock.paused or clock.time_ratio == 0:
        return None
    ic_elapsed = timedelta(
        seconds=(real_time - clock.anchor_real_time).total_seconds() * clock.time_ratio
    )
    return clock.anchor_ic_time + ic_elapsed


def validate_location_gap(
    location_id: int,
    scheduled_real_time: datetime,
    exclude_event_id: int | None = None,
) -> bool:
    """Check that no other event at this location is within LOCATION_GAP_HOURS.

    Returns True if the time slot is available.
    """
    window_start = scheduled_real_time - timedelta(hours=LOCATION_GAP_HOURS)
    window_end = scheduled_real_time + timedelta(hours=LOCATION_GAP_HOURS)
    qs = Event.objects.filter(
        location_id=location_id,
        scheduled_real_time__gte=window_start,
        scheduled_real_time__lte=window_end,
    ).exclude(status__in=[EventStatus.CANCELLED, EventStatus.COMPLETED])
    if exclude_event_id:
        qs = qs.exclude(id=exclude_event_id)
    return not qs.exists()


def create_event(  # noqa: PLR0913 - event creation requires all scheduling fields
    *,
    name: str,
    location_id: int,
    scheduled_real_time: datetime,
    host_persona: Persona,
    description: str = "",
    is_public: bool = True,
    scheduled_ic_time: datetime | None = None,
    time_phase: str = TimePhase.DAY,
    status: str = EventStatus.DRAFT,
) -> Event:
    """Create an event with a primary host.

    If scheduled_ic_time is not provided, it is derived from the game clock.
    Validates the location gap constraint before creating.

    Raises:
        EventError: If the location time slot is unavailable.
    """
    if not validate_location_gap(location_id, scheduled_real_time):
        raise EventError(EventError.LOCATION_GAP)

    if scheduled_ic_time is None:
        scheduled_ic_time = derive_ic_time_from_real(scheduled_real_time)
        if scheduled_ic_time is None:
            scheduled_ic_time = scheduled_real_time  # fallback if no clock

    event = Event.objects.create(
        name=name,
        description=description,
        location_id=location_id,
        status=status,
        is_public=is_public,
        scheduled_real_time=scheduled_real_time,
        scheduled_ic_time=scheduled_ic_time,
        time_phase=time_phase,
    )
    EventHost.objects.create(event=event, persona=host_persona, is_primary=True)
    return event


def schedule_event(event: Event) -> Event:
    """Transition an event from DRAFT to SCHEDULED."""
    if event.status != EventStatus.DRAFT:
        raise EventError(EventError.SCHEDULE_INVALID)
    event.status = EventStatus.SCHEDULED
    event.save(update_fields=["status", "updated_at"])
    return event


def _apply_room_overlay(event: Event) -> None:
    """Apply the event's room description overlay to the room's temporary description."""
    try:
        overlay = event.modification.room_description_overlay
    except EventModification.DoesNotExist:
        return
    if not overlay:
        return
    display_data, _ = ObjectDisplayData.objects.get_or_create(object_id=event.location_id)
    display_data.temporary_description = overlay
    display_data.save(update_fields=["temporary_description", "updated_date"])


def _revert_room_overlay(event: Event) -> None:
    """Clear the room's temporary description if it still matches this event's overlay.

    Only clears if the current temporary_description matches the event's overlay,
    so a subsequent event's overlay is not accidentally wiped.
    """
    try:
        overlay = event.modification.room_description_overlay
    except EventModification.DoesNotExist:
        return
    if not overlay:
        return
    try:
        display_data = ObjectDisplayData.objects.get(object_id=event.location_id)
    except ObjectDisplayData.DoesNotExist:
        return
    if display_data.temporary_description == overlay:
        display_data.temporary_description = ""
        display_data.save(update_fields=["temporary_description", "updated_date"])


def start_event(event: Event) -> Event:
    """Transition an event from SCHEDULED to ACTIVE and create a linked Scene.

    The Scene is created at the event's location with the event's name.
    Privacy mode auto-derived: public events get public scenes; private events
    require a non-public room (``Event.is_public`` is calendar visibility,
    distinct from ``RoomProfile.is_public`` which governs room listing).
    Starting a private event in a publicly-listed room is rejected with
    ``EventError.PRIVATE_IN_PUBLIC_ROOM``. Applies room description overlay
    if configured.

    Wraps scene creation + status update in a transaction. Uses
    select_for_update to prevent duplicate scenes from concurrent requests.

    Raises:
        EventError: If the event is not SCHEDULED, or if a private event is
            attempted in a publicly-listed room.
    """
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.status != EventStatus.SCHEDULED:
            raise EventError(EventError.START_INVALID)

        privacy = ScenePrivacyMode.PUBLIC if event.is_public else ScenePrivacyMode.PRIVATE
        if privacy != ScenePrivacyMode.PUBLIC and event.location.is_public:
            raise EventError(EventError.PRIVATE_IN_PUBLIC_ROOM)
        scene = Scene.objects.create(
            name=event.name,
            location=event.location.objectdb,
            privacy_mode=privacy,
            event=event,
        )
        # Link any accepted crossover invites to this freshly-spawned scene —
        # creates the EpisodeScene row for each invited story's accepted episode
        # and enrolls the invited Lead GM as a scene GM (#2002).
        from world.stories.services.crossover import (  # noqa: PLC0415
            link_accepted_invites_for_scene,
        )

        link_accepted_invites_for_scene(scene, event)

        _apply_room_overlay(event)

        event.status = EventStatus.ACTIVE
        event.started_at = timezone.now()
        event.save(update_fields=["status", "started_at", "updated_at"])
    return event


def _finish_event_scenes(event: Event) -> None:
    """Finish any active scenes linked to this event.

    Uses Scene.finish_scene() rather than bulk .update() to properly
    invalidate SharedMemoryModel's identity map cache. Awards scene
    completion rewards (vote budget bonuses) to all participants.
    """
    # At most one active scene per event (enforced by unique_active_scene_per_event constraint)
    for scene in Scene.objects.filter(event=event, is_active=True):
        scene.finish_scene()
        on_scene_finished(scene)


def complete_event(event: Event) -> Event:
    """Transition an event from ACTIVE to COMPLETED, finish linked scenes, and revert room."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.status != EventStatus.ACTIVE:
            raise EventError(EventError.COMPLETE_INVALID)
        _finish_event_scenes(event)
        _revert_room_overlay(event)
        event.status = EventStatus.COMPLETED
        event.ended_at = timezone.now()
        event.save(update_fields=["status", "ended_at", "updated_at"])
        _award_catering_prestige(event)
        _award_grandeur_prestige(event)
    return event


# --- Event catering → host prestige (#2852) ---------------------------------
# Mirrors the ceremony finish→prestige precedent: the one reward hook on event
# completion. Magnitudes PLACEHOLDER.

CATERING_PRESTIGE_ITEM_CAP = 12
CATERING_DEED_MINIMUM_SCORE = 2


def designate_catering_container(
    event: Event, contributor: "ObjectDB", container_instance: "ItemInstance"
) -> EventCatering:
    """Flag a container as catering for *event* (#2869).

    The vessel keeps living its life — it is not consumed, moved, or locked.
    From here on, any consumable put into it tags for this event and counts
    toward the host's Hospitality prestige. Re-flagging is idempotent.
    """
    if event.status not in (EventStatus.SCHEDULED, EventStatus.ACTIVE):
        raise EventError(EventError.CATER_INVALID)
    if not container_instance.template.is_container:
        raise EventError(EventError.CATER_NOT_CONTAINER)
    persona = _contributor_persona(contributor)
    if persona is None:
        raise EventError(EventError.CATER_NO_PERSONA)
    row, _created = EventCatering.objects.get_or_create(
        event=event,
        item_instance=container_instance,
        defaults={"role": CateringRole.CONTAINER, "contributed_by": persona},
    )
    return row


def catering_event_for_container(container_instance: "ItemInstance") -> Event | None:
    """The open event this container is currently catering, if any (#2869)."""
    row = (
        EventCatering.objects.filter(
            item_instance=container_instance,
            role=CateringRole.CONTAINER,
            event__status__in=(EventStatus.SCHEDULED, EventStatus.ACTIVE),
        )
        .select_related("event")
        .order_by("-created_at")
        .first()
    )
    return row.event if row is not None else None


def tag_catered_provision(
    item_instance: "ItemInstance",
    container_instance: "ItemInstance",
    contributor: "ObjectDB | None" = None,
) -> EventCatering | None:
    """Tag a consumable set out in a catering vessel (#2869).

    Called from the put-in path. Non-consumables and un-flagged containers
    are silently ignored — putting a knife in a banquet table is just
    storage. The tag is permanent and deduped per (event, item): taking the
    dish back out (or eating it) never untags it, and shuffling it in and
    out cannot farm prestige.
    """
    if not item_instance.template.is_consumable:
        return None
    event = catering_event_for_container(container_instance)
    if event is None:
        return None
    row, _created = EventCatering.objects.get_or_create(
        event=event,
        item_instance=item_instance,
        defaults={
            "role": CateringRole.PROVISION,
            "contributed_by": _contributor_persona(contributor),
        },
    )
    return row


def catering_history(item_instance: "ItemInstance") -> list[EventCatering]:
    """Every event this item has served at, newest first (#2869) — the souvenir."""
    return list(EventCatering.objects.filter(item_instance=item_instance).select_related("event"))


def _contributor_persona(contributor: "ObjectDB | None"):
    """The acting persona behind a catering act, or None."""
    if contributor is None:
        return None
    sheet = contributor.character_sheet
    if sheet is None:
        return None
    return sheet.active_persona or sheet.primary_persona


def _catering_score(event: Event) -> int:
    """Sum of quality multipliers over the tagged provisions, capped (#2869).

    Reads the live items — the spread is whatever was set out, whether or
    not it is still sitting in the vessel when the night ends.
    """
    rows = list(
        event.catering.filter(role=CateringRole.PROVISION).select_related(
            "item_instance__quality_tier"
        )[:CATERING_PRESTIGE_ITEM_CAP]
    )
    total = 0.0
    for row in rows:
        tier = row.item_instance.quality_tier
        total += float(tier.stat_multiplier) if tier is not None else 1.0
    return round(total)


def _award_catering_prestige(event: Event) -> None:
    """The host's prestige and their house's stature from a catered spread.

    Minted a Hospitality *Legend deed* until #3463. A feast risks nothing, so
    under the bard test it is worth no song — prestige and stature only. The
    function keeps its name because prestige is what it was always for; the
    legend deed was the part that did not belong.
    """
    score = _catering_score(event)
    if score < CATERING_DEED_MINIMUM_SCORE:
        return
    host = (
        EventHost.objects.filter(event=event, is_primary=True).select_related("persona").first()
        or EventHost.objects.filter(event=event).select_related("persona").first()
    )
    if host is None or host.persona is None:
        return
    _apply_grand_display(host.persona, score)


def _apply_grand_display(persona, score: int) -> None:
    """A lavish enough spread is a grand display (#3093): the host's house
    looks stronger than the ledgers say. Bounded upward bluff — the mirror
    of whisper campaigns."""
    from world.societies.houses.stature_services import apply_grand_display  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    membership = (
        OrganizationMembership.objects.filter(
            persona=persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
            organization__family__isnull=False,
        )
        .select_related("organization", "rank")
        .order_by("rank__tier")
        .first()
    )
    if membership is None:
        return
    apply_grand_display(membership.organization, score)


# --- Event grandeur → host/honoree prestige (#2357) --------------------------
# Catering-shaped sibling for the once-in-a-lifetime event spend (wedding,
# coronation, grand ball): a currency sink recorded per contribution, summed
# into a sqrt-diminishing-returns score at completion, minted via the same
# create_solo_deed + apply_grand_display pipeline catering uses. Ratified
# 2026-08-15: for ceremony-linked (WEDDING/CORONATION) events the economic
# cost IS the gate — no is_milestone flag, no cooldown bookkeeping; plain
# diminishing returns apply to every event alike. All magnitudes PLACEHOLDER.

GRANDEUR_COPPER_TO_POINT_RATE = 1000
GRANDEUR_SCORE_CAP = 40
GRANDEUR_DEED_MINIMUM_SCORE = 3


# Ceremony type keys whose honorees get an additive grandeur cut (#2357 amendments).
# "coronation" is not yet a valid CeremonyTypeKey choice (lands with #2358) — the
# plain string check is forward-compatible: no Ceremony row can carry that key
# until #2358 adds it, so this simply never matches until then.
def contribute_grandeur(  # noqa: PLR0913 - purse/treasury source pair is co-equal, mirrors transfer()
    event: Event,
    persona: Persona,
    *,
    category: str,
    amount: int,
    from_purse: "CharacterPurse | None" = None,
    from_treasury: "OrganizationTreasury | None" = None,
) -> EventGrandeurContribution:
    """Spend on an event's grandeur budget — a currency sink tagged per category (#2357).

    Mirrors ``designate_catering_container``'s shape: validates the event is
    still open for contribution, moves the money through the audited
    ``currency.services.transfer`` sink (null destination), then records the
    tagged row. The purse-vs-treasury source and any treasury spend-authority
    check are the caller's responsibility (the Action layer, mirroring
    catering's contributor resolution) — this function just moves the money
    and tags it.

    **Nonrefundable by design** (ruled by the controller 2026-08-15, spec
    silent): a SCHEDULED event can take contributions and later be
    ``cancel_event``'d — there is no grandeur-specific unwind on cancellation.
    ``transfer``'s null destination is a genuine sink (the coppers are gone,
    not parked anywhere recoverable), and no prestige is minted either
    (``_award_grandeur_prestige`` only ever runs from ``complete_event``). This
    reads as a nonrefundable-deposit flavor — throwing money at a wedding that
    falls through doesn't buy it back — rather than an oversight; revisit if
    that flavor call turns out wrong.

    Raises:
        EventError: If the event is not SCHEDULED/ACTIVE, or funds are short.
    """
    if event.status not in (EventStatus.SCHEDULED, EventStatus.ACTIVE):
        raise EventError(EventError.GRANDEUR_INVALID)
    from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

    from world.currency.services import transfer  # noqa: PLC0415

    try:
        row = transfer(
            amount=amount,
            reason=f"Grandeur investment: {category} at {event.name}",
            from_purse=from_purse,
            from_treasury=from_treasury,
        )
    except DjangoValidationError as exc:
        raise EventError(EventError.GRANDEUR_INSUFFICIENT_FUNDS) from exc
    return EventGrandeurContribution.objects.create(
        event=event,
        category=category,
        contributed_by=persona,
        amount_spent=amount,
        transfer=row,
    )


def _grandeur_score(event: Event) -> int:
    """Sqrt-diminishing-returns score off total grandeur spend, capped (#2357).

    A house that dumps 10x the coppers gets ~3x the score, not 10x — the
    diminishing-returns lever the issue asks for. Reads the live rows, same
    shape as ``_catering_score``.
    """
    total_spent = (
        EventGrandeurContribution.objects.filter(event=event).aggregate(total=Sum("amount_spent"))[
            "total"
        ]
        or 0
    )
    if total_spent <= 0:
        return 0
    points = total_spent / GRANDEUR_COPPER_TO_POINT_RATE
    return min(GRANDEUR_SCORE_CAP, round(math.sqrt(points)))


def _award_grandeur_prestige(event: Event) -> None:
    """The host's prestige and stature from the event's spend (#2357).

    Minted a Grandeur *Legend deed* until #3463; coin buys fame and stature,
    never Legend. The honoree cut went with it — see
    ``_award_grandeur_honoree_cut``.
    """
    score = _grandeur_score(event)
    if score < GRANDEUR_DEED_MINIMUM_SCORE:
        return
    host = (
        EventHost.objects.filter(event=event, is_primary=True).select_related("persona").first()
        or EventHost.objects.filter(event=event).select_related("persona").first()
    )
    if host is None or host.persona is None:
        return
    _apply_grand_display(host.persona, score)


def cancel_event(event: Event) -> Event:
    """Cancel an event from DRAFT or SCHEDULED status."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.status in (EventStatus.COMPLETED, EventStatus.CANCELLED):
            raise EventError(EventError.CANCEL_TERMINAL)
        if event.status == EventStatus.ACTIVE:
            raise EventError(EventError.CANCEL_ACTIVE)
        event.status = EventStatus.CANCELLED
        event.ended_at = timezone.now()
        event.save(update_fields=["status", "ended_at", "updated_at"])
    return event


def add_host(event: Event, persona: Persona, *, is_primary: bool = False) -> EventHost:
    """Add a host to an event."""
    return EventHost.objects.create(event=event, persona=persona, is_primary=is_primary)


def invite_persona(
    event: Event,
    target_persona: Persona,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite a persona to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.PERSONA,
        target_persona=target_persona,
        invited_by=invited_by,
    )


def invite_organization(
    event: Event,
    organization: Organization,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite an organization to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.ORGANIZATION,
        target_organization=organization,
        invited_by=invited_by,
    )


def invite_society(
    event: Event,
    society: Society,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite a society to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.SOCIETY,
        target_society=society,
        invited_by=invited_by,
    )


def set_room_description_overlay(event: Event, overlay_text: str) -> EventModification:
    """Set or update the room description overlay for an event."""
    mod, _ = EventModification.objects.update_or_create(
        event=event,
        defaults={"room_description_overlay": overlay_text},
    )
    return mod


def get_visible_events(
    persona: Persona | None = None,
    *,
    include_public: bool = True,
) -> QuerySet[Event]:
    """Return events visible to a persona.

    Public events are always included (if include_public=True).
    Private events are included if the persona is a host, directly invited,
    or a member of an invited organization or society.
    """
    qs = Event.objects.exclude(status=EventStatus.CANCELLED)

    if persona is None:
        return qs.filter(is_public=True) if include_public else qs.none()

    public_q = Q(is_public=True) if include_public else Q()
    host_q = Q(hosts__persona=persona)
    direct_invite_q = Q(
        invitations__target_type=InvitationTargetType.PERSONA,
        invitations__target_persona=persona,
    )
    org_invite_q = Q(
        invitations__target_type=InvitationTargetType.ORGANIZATION,
        invitations__target_organization__memberships__persona=persona,
    )
    society_invite_q = Q(
        invitations__target_type=InvitationTargetType.SOCIETY,
        invitations__target_society__organizations__memberships__persona=persona,
    )

    return qs.filter(
        public_q | host_q | direct_invite_q | org_invite_q | society_invite_q
    ).distinct()


def respond_to_invitation(
    invitation: EventInvitation,
    persona: Persona,
    *,
    response: str,
) -> EventInvitation:
    """Record an invitee's RSVP (ACCEPTED / DECLINED) on a PERSONA invitation.

    Only persona-targeted invitations carry an RSVP — an org/society invitation
    has no per-member row. The *persona* must be the invitation's
    ``target_persona`` (the invitee themselves). Setting the response is
    idempotent: re-responding toggles/overwrites the prior value and refreshes
    ``responded_at``.

    Raises:
        EventError: if the invitation is not a persona invite, does not target
            this persona, or belongs to an ACTIVE/COMPLETED/CANCELLED event.
    """
    if invitation.target_type != InvitationTargetType.PERSONA:
        raise EventError(EventError.RSVP_NOT_PERSONA)
    if invitation.target_persona_id != persona.pk:
        raise EventError(EventError.RSVP_NOT_YOURS)
    # RSVP only while the event is still open (DRAFT/SCHEDULED). Once active or
    # finished the host has moved past the headcount.
    if invitation.event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
        raise EventError(EventError.RSVP_CLOSED)
    invitation.response = response
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["response", "responded_at"])
    return invitation
