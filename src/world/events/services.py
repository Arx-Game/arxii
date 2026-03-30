"""Service functions for event lifecycle, invitations, and visibility."""

from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from evennia_extensions.models import ObjectDisplayData
from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.events.types import EventError
from world.game_clock.constants import TimePhase
from world.game_clock.models import GameClock
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
    display_data, _ = ObjectDisplayData.objects.get_or_create(object_id=event.location.objectdb_id)
    display_data.temporary_description = overlay
    display_data.save(update_fields=["temporary_description", "updated_date"])


def _revert_room_overlay(event: Event) -> None:
    """Clear the room's temporary description after an event ends."""
    try:
        overlay = event.modification.room_description_overlay
    except EventModification.DoesNotExist:
        return
    if not overlay:
        return
    try:
        display_data = ObjectDisplayData.objects.get(object_id=event.location.objectdb_id)
    except ObjectDisplayData.DoesNotExist:
        return
    display_data.temporary_description = ""
    display_data.save(update_fields=["temporary_description", "updated_date"])


def start_event(event: Event) -> Event:
    """Transition an event from SCHEDULED to ACTIVE and create a linked Scene.

    The Scene is created at the event's location with the event's name.
    Privacy mode auto-derived: public events get public scenes, private events
    get private scenes. Applies room description overlay if configured.

    Wraps scene creation + status update in a transaction. Uses
    select_for_update to prevent duplicate scenes from concurrent requests.
    """
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.status != EventStatus.SCHEDULED:
            raise EventError(EventError.START_INVALID)

        privacy = ScenePrivacyMode.PUBLIC if event.is_public else ScenePrivacyMode.PRIVATE
        Scene.objects.create(
            name=event.name,
            location=event.location.objectdb,
            privacy_mode=privacy,
            event=event,
        )

        _apply_room_overlay(event)

        event.status = EventStatus.ACTIVE
        event.started_at = timezone.now()
        event.save(update_fields=["status", "started_at", "updated_at"])
    return event


def _finish_event_scenes(event: Event) -> None:
    """Finish any active scenes linked to this event.

    Uses Scene.finish_scene() rather than bulk .update() to properly
    invalidate SharedMemoryModel's identity map cache.
    """
    # At most one active scene per event (enforced by unique_active_scene_per_event constraint)
    for scene in Scene.objects.filter(event=event, is_active=True):
        scene.finish_scene()


def complete_event(event: Event) -> Event:
    """Transition an event from ACTIVE to COMPLETED, finish linked scenes, and revert room."""
    with transaction.atomic():
        if event.status != EventStatus.ACTIVE:
            raise EventError(EventError.COMPLETE_INVALID)
        _finish_event_scenes(event)
        _revert_room_overlay(event)
        event.status = EventStatus.COMPLETED
        event.ended_at = timezone.now()
        event.save(update_fields=["status", "ended_at", "updated_at"])
    return event


def cancel_event(event: Event) -> Event:
    """Cancel an event from DRAFT or SCHEDULED status."""
    with transaction.atomic():
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
