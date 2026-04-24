"""Scheduling-related services: SessionRequest creation and lifecycle management.

Public API:
    maybe_create_session_request(progress) — idempotently create an OPEN
        SessionRequest when the current episode is ready-to-run and requires
        GM involvement. Returns the existing or new request, or None when the
        episode is not yet eligible or needs no GM.

    create_event_from_session_request(...) — bridge an OPEN SessionRequest
        to the events system: creates an Event, links it, transitions status
        to SCHEDULED.

    cancel_session_request(session_request) — mark OPEN -> CANCELLED.

    resolve_session_request(session_request) — mark SCHEDULED -> RESOLVED
        after the session has been run.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.db import transaction

from world.stories.constants import BeatPredicateType, SessionRequestStatus, TransitionMode
from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.models import SessionRequest

if TYPE_CHECKING:
    from world.events.models import Event
    from world.scenes.models import Persona
    from world.stories.types import AnyStoryProgress


def maybe_create_session_request(progress: AnyStoryProgress) -> SessionRequest | None:
    """Create an OPEN SessionRequest if the current episode is ready-to-run.

    Called from write-path services (record_gm_marked_outcome,
    record_aggregate_contribution, evaluate_auto_beats) after they update
    beat state. Idempotent: if an OPEN or SCHEDULED SessionRequest already
    exists for this episode, returns the existing one without creating a
    duplicate.

    Returns the SessionRequest if one was created or already exists;
    returns None if the current episode isn't ready or needs no GM.

    Eligibility criteria (ALL must be true):
        1. progress.current_episode is not None
        2. get_eligible_transitions(progress) is non-empty
        3. The target episode requires GM involvement — indicated by ANY
           eligible transition being mode=GM_CHOICE, OR any of the current
           episode's beats being predicate_type=GM_MARKED and still
           UNSATISFIED (a session is needed to mark them).

    Criterion 3 detail: we check the *current* episode for GM_MARKED beats
    (at least one still UNSATISFIED means a GM session is needed to make
    progress), and also check outbound transitions for GM_CHOICE mode (Lead
    GM must pick the path). Either condition is sufficient.
    """
    # Defer import to avoid circular import — beats.py imports from models.py
    # which is shared, but scheduling.py would create a mutual import with
    # transitions.py if not deferred.
    from world.stories.constants import BeatOutcome  # noqa: PLC0415
    from world.stories.services.transitions import get_eligible_transitions  # noqa: PLC0415

    if progress.current_episode is None:
        return None

    try:
        eligible = list(get_eligible_transitions(progress))
    except ProgressionRequirementNotMetError:
        # Progression requirements are not yet met — no session request needed.
        return None

    if not eligible:
        return None

    episode = progress.current_episode

    # Check whether GM involvement is required.
    # Case A: any eligible outbound transition requires a GM to choose the path.
    needs_gm = any(t.mode == TransitionMode.GM_CHOICE for t in eligible)

    if not needs_gm:
        # Case B: the current episode has at least one GM_MARKED beat that is
        # still UNSATISFIED — a GM session is needed to mark it.
        needs_gm = episode.beats.filter(
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        ).exists()

    if not needs_gm:
        # No GM required; the episode can self-advance without a session.
        return None

    # Idempotent: return existing OPEN or SCHEDULED request if one exists.
    existing = SessionRequest.objects.filter(
        episode=episode,
        status__in=[SessionRequestStatus.OPEN, SessionRequestStatus.SCHEDULED],
    ).first()
    if existing is not None:
        return existing

    return SessionRequest.objects.create(
        episode=episode,
        status=SessionRequestStatus.OPEN,
    )


def create_event_from_session_request(  # noqa: PLR0913 — event scheduling requires all scheduling fields
    *,
    session_request: SessionRequest,
    name: str,
    scheduled_real_time: datetime,
    host_persona: Persona,
    location_id: int,
    description: str = "",
    is_public: bool = True,
) -> Event:
    """Turn an OPEN SessionRequest into a scheduled Event.

    Validates that the SessionRequest is OPEN. Creates the Event via
    events.services.create_event (which validates the location gap and
    derives IC time from the game clock). Links the Event back to the
    SessionRequest and transitions SessionRequest.status to SCHEDULED.

    Args:
        session_request: Must be in OPEN status.
        name: Event name (shown on the calendar).
        scheduled_real_time: OOC datetime players will attend.
        host_persona: The Persona listed as primary event host.
        location_id: RoomProfile PK where the session takes place.
        description: Optional event description.
        is_public: Whether the event appears on the public calendar.

    Returns:
        The newly created Event.

    Raises:
        EventError: If the location time slot is unavailable (from events.services).

    Defensive assertion: CreateEventFromSessionRequestInputSerializer validates OPEN status
    for API callers. Race condition: assertion fires if status changes between validation
    and this call — acceptable for an infrequent edge case.
    """
    from world.events.services import create_event  # noqa: PLC0415

    if session_request.status != SessionRequestStatus.OPEN:
        msg = (
            f"SessionRequest {session_request.pk} is not OPEN "
            f"(status={session_request.status!r}); "
            "CreateEventFromSessionRequestInputSerializer should have rejected this."
        )
        raise ValueError(msg)

    with transaction.atomic():
        event = create_event(
            name=name,
            location_id=location_id,
            scheduled_real_time=scheduled_real_time,
            host_persona=host_persona,
            description=description,
            is_public=is_public,
        )
        session_request.event = event
        session_request.status = SessionRequestStatus.SCHEDULED
        session_request.save(update_fields=["event", "status", "updated_at"])

    return event


def cancel_session_request(*, session_request: SessionRequest) -> SessionRequest:
    """Mark a SessionRequest as CANCELLED.

    Defensive assertion: CancelSessionRequestInputSerializer validates OPEN status
    for API callers. Race condition: assertion fires if status changes between
    validation and this call — acceptable for an infrequent edge case.
    """
    if session_request.status != SessionRequestStatus.OPEN:
        msg = (
            f"SessionRequest {session_request.pk} is not OPEN "
            f"(status={session_request.status!r}); "
            "CancelSessionRequestInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    session_request.status = SessionRequestStatus.CANCELLED
    session_request.save(update_fields=["status", "updated_at"])
    return session_request


def resolve_session_request(*, session_request: SessionRequest) -> SessionRequest:
    """Mark a scheduled SessionRequest as RESOLVED after the session ran.

    Defensive assertion: ResolveSessionRequestInputSerializer validates SCHEDULED status
    for API callers. Race condition: assertion fires if status changes between
    validation and this call — acceptable for an infrequent edge case.
    """
    if session_request.status != SessionRequestStatus.SCHEDULED:
        msg = (
            f"SessionRequest {session_request.pk} is not SCHEDULED "
            f"(status={session_request.status!r}); "
            "ResolveSessionRequestInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    session_request.status = SessionRequestStatus.RESOLVED
    session_request.save(update_fields=["status", "updated_at"])
    return session_request
