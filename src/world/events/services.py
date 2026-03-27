"""Service functions for event lifecycle, invitations, and visibility."""

from datetime import datetime, timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.game_clock.constants import TimePhase
from world.game_clock.models import GameClock
from world.scenes.models import Persona

# Minimum gap between events at the same location (real hours)
LOCATION_GAP_HOURS = 6

# Error messages
_ERR_LOCATION_GAP = (
    f"Another event is scheduled within {LOCATION_GAP_HOURS} hours at this location."
)
_ERR_CANCEL_COMPLETED = "Cannot cancel a completed event."


def _status_transition_error(action: str, status: str) -> str:
    return f"Cannot {action} event in '{status}' status."


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
    ).exclude(status=EventStatus.CANCELLED)
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
        ValueError: If the location time slot is unavailable.
    """
    if not validate_location_gap(location_id, scheduled_real_time):
        raise ValueError(_ERR_LOCATION_GAP)

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
        msg = _status_transition_error("schedule", event.status)
        raise ValueError(msg)
    event.status = EventStatus.SCHEDULED
    event.save(update_fields=["status", "updated_at"])
    return event


def start_event(event: Event) -> Event:
    """Transition an event from SCHEDULED to ACTIVE."""
    if event.status != EventStatus.SCHEDULED:
        msg = _status_transition_error("start", event.status)
        raise ValueError(msg)
    event.status = EventStatus.ACTIVE
    event.started_at = timezone.now()
    event.save(update_fields=["status", "started_at", "updated_at"])
    return event


def complete_event(event: Event) -> Event:
    """Transition an event from ACTIVE to COMPLETED."""
    if event.status != EventStatus.ACTIVE:
        msg = _status_transition_error("complete", event.status)
        raise ValueError(msg)
    event.status = EventStatus.COMPLETED
    event.ended_at = timezone.now()
    event.save(update_fields=["status", "ended_at", "updated_at"])
    return event


def cancel_event(event: Event) -> Event:
    """Cancel an event from any non-completed status."""
    if event.status == EventStatus.COMPLETED:
        raise ValueError(_ERR_CANCEL_COMPLETED)
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
    organization_id: int,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite an organization to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.ORGANIZATION,
        target_organization_id=organization_id,
        invited_by=invited_by,
    )


def invite_society(
    event: Event,
    society_id: int,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite a society to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.SOCIETY,
        target_society_id=society_id,
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
    Private events are included if the persona is a host or invitee
    (directly or via organization/society membership).
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

    return qs.filter(public_q | host_q | direct_invite_q).distinct()
