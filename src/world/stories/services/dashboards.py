"""Dashboard service helpers for Wave 10 aggregate-view endpoints.

Public API:
    compute_story_status_line(progress) — player-facing one-liner
        summarising where a story currently stands.
"""

from __future__ import annotations

from world.stories.constants import SessionRequestStatus
from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.types import AnyStoryProgress

# Days before a story's last_advanced_at is considered stale.
STALE_STORY_DAYS = 14


def _session_request_status_line(ep_label: str, episode: object) -> str:
    """Return a status line based on any open/scheduled SessionRequest for an episode."""
    from world.stories.models import SessionRequest  # noqa: PLC0415

    session_req = (
        SessionRequest.objects.filter(
            episode=episode,
            status__in=[SessionRequestStatus.OPEN, SessionRequestStatus.SCHEDULED],
        )
        .select_related("event")
        .first()
    )

    if session_req is None:
        return f"{ep_label} — ready to resolve"

    if session_req.status == SessionRequestStatus.OPEN:
        return f"{ep_label} — ready to schedule"

    # SCHEDULED — try to format the event time.
    event = session_req.event
    if event is not None and event.scheduled_real_time is not None:
        event_time = event.scheduled_real_time.strftime("%Y-%m-%d %H:%M UTC")
        return f"{ep_label} — scheduled for {event_time}"

    return f"{ep_label} — scheduled for tbd"


def compute_story_status_line(progress: AnyStoryProgress) -> str:
    """Build a player-facing one-liner summarising where a story is.

    Format:
    - "on hold"                           — frontier (no episode authored yet)
    - "Ch{N} Ep{M} — waiting on you"     — progression requirements not met
    - "Ch{N} Ep{M} — on hold"            — no outbound transitions authored yet
    - "Ch{N} Ep{M} — ready to schedule"  — open SessionRequest exists
    - "Ch{N} Ep{M} — scheduled for …"    — scheduled SessionRequest
    - "Ch{N} Ep{M} — ready to resolve"   — auto-resolvable transitions ready
    """
    from world.stories.services.transitions import get_eligible_transitions  # noqa: PLC0415

    if progress.current_episode is None:
        return "on hold"

    episode = progress.current_episode
    chapter = episode.chapter
    ep_label = f"Ch{chapter.order} Ep{episode.order}"

    try:
        eligible = get_eligible_transitions(progress)
    except ProgressionRequirementNotMetError:
        return f"{ep_label} — waiting on you"

    if not eligible:
        return f"{ep_label} — on hold"

    return _session_request_status_line(ep_label, episode)
