"""Dashboard service helpers for Wave 10 aggregate-view endpoints.

Public API:
    compute_story_status(progress) — returns a StoryStatusSummary dataclass
        describing where a story currently stands. Callers render their own
        labels; the service does not return human-readable strings.
    compute_story_status_line(progress) — returns the deliberately-ambiguous
        player-facing one-liner for a story's dashboard. Player copy never
        implies finality at a rest/pause (no "over"/"done"/"complete"/"the
        end"); it is reassuring at WAITING_FOR_GM. GM/staff dashboards use the
        structured status + last_advanced_at instead of this string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.constants import (
    ProgressStatus,
    SessionRequestStatus,
    StoryEpisodeStatus,
    StoryScope,
)
from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.models import Episode, GlobalStoryProgress, GroupStoryProgress, StoryProgress
from world.stories.types import (
    AnyStoryProgress,
    MyActiveStoriesResult,
    MyActiveStoryEntry,
    StoryStatusSummary,
)

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser

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


def compute_story_status_line(progress: AnyStoryProgress) -> str:
    """Return the player-facing one-liner for a story's dashboard.

    Branches on progress.status FIRST — before any logic that assumes an
    ACTIVE pointer with eligible transitions. The copy is deliberately
    ambiguous at a pause/rest so it never implies the story is finished
    (no "over"/"done"/"complete"/"the end"), and reassuring at
    WAITING_FOR_GM so a player knows their GM has the ball.
    """
    # Terminal / paused states: deliberate copy that never implies the story is
    # finished at a pause/rest (no "over"/"done"/"the end"), and is reassuring
    # at WAITING_FOR_GM so a player knows their GM has the ball.
    terminal_lines: dict[str, str] = {
        ProgressStatus.WAITING_FOR_GM: (
            "The trail goes quiet — your GM has been notified. More to come."
        ),
        ProgressStatus.RESTING: "The story rests here for now.",
        ProgressStatus.COMPLETED: "This story has reached its conclusion.",
    }
    line = terminal_lines.get(progress.status)
    if line is not None:
        return line
    if progress.status == ProgressStatus.FORECLOSED:
        return (
            "This thread has been closed."
            if progress.resolved_at is not None
            else (
                "This thread was left unresolved when its story concluded. "
                "A GM can wrap it up for you."
            )
        )

    # ACTIVE — describe the current position from the structured summary.
    summary = compute_story_status(progress)
    if summary.episode_title is None:
        return "Your story is being prepared. Check back soon."
    return f"Currently in “{summary.episode_title}.” The story continues."


def _serialize_progress_entry(progress: AnyStoryProgress, scope: str) -> MyActiveStoryEntry:
    """Build the dict shape shared by all three scope collectors below."""
    story = progress.story
    episode = progress.current_episode
    summary = compute_story_status(progress)

    current_episode_id: int | None = episode.pk if episode is not None else None

    return {
        "story_id": story.pk,
        "story_title": story.title,
        "scope": scope,
        "current_episode_id": current_episode_id,
        "current_episode_title": summary.episode_title,
        "chapter_title": summary.chapter_title,
        "status": summary.status,
        "status_label": StoryEpisodeStatus(summary.status).label,
        "progress_status": progress.status,
        "chapter_order": summary.chapter_order,
        "episode_order": summary.episode_order,
        "open_session_request_id": summary.open_session_request_id,
        "scheduled_event_id": summary.scheduled_event_id,
        "scheduled_real_time": summary.scheduled_real_time,
    }


def _collect_character_stories(
    account: AbstractBaseUser | AnonymousUser,
) -> list[MyActiveStoryEntry]:
    """Return active CHARACTER-scope progress entries owned by this account."""
    qs = StoryProgress.objects.filter(
        story__character_sheet__character__db_account=account,
        is_active=True,
    ).select_related(
        "story",
        "current_episode",
        "current_episode__chapter",
    )
    return [_serialize_progress_entry(p, StoryScope.CHARACTER) for p in qs]


def _collect_group_stories(
    account: AbstractBaseUser | AnonymousUser,
) -> list[MyActiveStoryEntry]:
    """Return active GROUP-scope progress entries for tables this account belongs to."""
    qs = (
        GroupStoryProgress.objects.filter(
            gm_table__memberships__persona__character_sheet__character__db_account=account,
            gm_table__memberships__left_at__isnull=True,
            is_active=True,
        )
        .select_related(
            "story",
            "current_episode",
            "current_episode__chapter",
        )
        .distinct()
    )
    return [_serialize_progress_entry(p, StoryScope.GROUP) for p in qs]


def _collect_global_stories(
    account: AbstractBaseUser | AnonymousUser,
) -> list[MyActiveStoryEntry]:
    """Return active GLOBAL-scope progress entries where the account has a StoryParticipation."""
    qs = (
        GlobalStoryProgress.objects.filter(
            story__participants__character__db_account=account,
            story__participants__is_active=True,
            is_active=True,
        )
        .select_related(
            "story",
            "current_episode",
            "current_episode__chapter",
        )
        .distinct()
    )
    return [_serialize_progress_entry(p, StoryScope.GLOBAL) for p in qs]


def active_stories_for_account(
    account: AbstractBaseUser | AnonymousUser,
) -> MyActiveStoriesResult:
    """Active stories across all three scopes (CHARACTER / GROUP / GLOBAL) for *account*.

    The shared seam behind both ``MyActiveStoriesView`` (web) and the telnet
    ``story list`` subverb (#1853) — one query path, not two parallel
    implementations of "what are my active stories."
    """
    return {
        "character_stories": _collect_character_stories(account),
        "group_stories": _collect_group_stories(account),
        "global_stories": _collect_global_stories(account),
    }
