"""Dashboard service helpers for Wave 10 aggregate-view endpoints.

Public API:
    compute_story_status(progress) — returns a StoryStatusSummary dataclass
        describing where a story currently stands. Callers render their own
        labels; the service does not return human-readable strings.
"""

from __future__ import annotations

from world.stories.constants import SessionRequestStatus, StoryEpisodeStatus
from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.models import Episode
from world.stories.types import AnyStoryProgress, StoryStatusSummary

# Days before a story's last_advanced_at is considered stale.
STALE_STORY_DAYS = 14


def _resolve_session_request(episode: Episode) -> StoryStatusSummary | None:
    """Return a StoryStatusSummary if there is an open/scheduled SessionRequest for an episode.

    Returns None if no relevant SessionRequest exists.
    """
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
        return None

    chapter = episode.chapter
    if session_req.status == SessionRequestStatus.OPEN:
        return StoryStatusSummary(
            status=StoryEpisodeStatus.READY_TO_SCHEDULE,
            chapter_order=chapter.order,
            chapter_title=chapter.title,
            episode_order=episode.order,
            episode_title=episode.title,
            open_session_request_id=session_req.pk,
            scheduled_event_id=None,
            scheduled_real_time=None,
        )

    # SCHEDULED — event may have a real time.
    event = session_req.event
    scheduled_real_time = event.scheduled_real_time if event is not None else None
    return StoryStatusSummary(
        status=StoryEpisodeStatus.SCHEDULED,
        chapter_order=chapter.order,
        chapter_title=chapter.title,
        episode_order=episode.order,
        episode_title=episode.title,
        open_session_request_id=session_req.pk,
        scheduled_event_id=session_req.event_id,
        scheduled_real_time=scheduled_real_time,
    )


def compute_story_status(progress: AnyStoryProgress) -> StoryStatusSummary:
    """Build a structured status summary for where a story currently stands.

    Returns a StoryStatusSummary with:
    - status: a StoryEpisodeStatus value (callers render their own label)
    - chapter_order / chapter_title / episode_order / episode_title: current position
    - open_session_request_id / scheduled_event_id / scheduled_real_time: scheduling info

    Status values:
    - ON_HOLD              — frontier (no episode authored yet) or no outbound transitions
    - WAITING_ON_BEATS     — progression requirements not met
    - READY_TO_SCHEDULE    — open SessionRequest exists
    - SCHEDULED            — scheduled SessionRequest with event
    - READY_TO_RESOLVE     — auto-resolvable transitions ready, no SessionRequest
    """
    from world.stories.services.transitions import get_eligible_transitions  # noqa: PLC0415

    if progress.current_episode is None:
        return StoryStatusSummary(
            status=StoryEpisodeStatus.ON_HOLD,
            chapter_order=None,
            chapter_title=None,
            episode_order=None,
            episode_title=None,
            open_session_request_id=None,
            scheduled_event_id=None,
            scheduled_real_time=None,
        )

    episode = progress.current_episode
    chapter = episode.chapter

    try:
        eligible = get_eligible_transitions(progress)
    except ProgressionRequirementNotMetError:
        return StoryStatusSummary(
            status=StoryEpisodeStatus.WAITING_ON_BEATS,
            chapter_order=chapter.order,
            chapter_title=chapter.title,
            episode_order=episode.order,
            episode_title=episode.title,
            open_session_request_id=None,
            scheduled_event_id=None,
            scheduled_real_time=None,
        )

    if not eligible:
        return StoryStatusSummary(
            status=StoryEpisodeStatus.ON_HOLD,
            chapter_order=chapter.order,
            chapter_title=chapter.title,
            episode_order=episode.order,
            episode_title=episode.title,
            open_session_request_id=None,
            scheduled_event_id=None,
            scheduled_real_time=None,
        )

    # Eligible transitions exist — check for a SessionRequest.
    session_summary = _resolve_session_request(episode)
    if session_summary is not None:
        return session_summary

    return StoryStatusSummary(
        status=StoryEpisodeStatus.READY_TO_RESOLVE,
        chapter_order=chapter.order,
        chapter_title=chapter.title,
        episode_order=episode.order,
        episode_title=episode.title,
        open_session_request_id=None,
        scheduled_event_id=None,
        scheduled_real_time=None,
    )
