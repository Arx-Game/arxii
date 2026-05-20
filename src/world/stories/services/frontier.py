"""Frontier resolution: when a player can't advance, decide whether the
story is WAITING_FOR_GM (immature content remains) or RESTING (nothing
authored remains — deliberately ambiguous, never COMPLETED)."""

from world.stories.constants import ProgressStatus, StoryMaturity
from world.stories.models import Episode
from world.stories.types import AnyStoryProgress


def set_progress_status(progress: AnyStoryProgress, status: ProgressStatus) -> None:
    """Set status on any progress type. COMPLETED also clears is_active;
    every other status keeps is_active True (the story is still live, just
    paused)."""
    progress.status = status
    progress.is_active = status != ProgressStatus.COMPLETED
    # last_advanced_at is auto_now; omitting it from update_fields preserves
    # its prior value. A status-only flip is NOT a forward advance, so the
    # staleness clock (days_waiting / stale_stories) must not be reset here.
    progress.save(update_fields=["status", "is_active"])


def _story_has_immature_content(story_id: int) -> bool:
    """True if any Episode in the story is still PITCH/OUTLINE — i.e. the
    author intends more. Story-wide heuristic; per-DAG-reachability
    refinement is a documented follow-up."""
    return (
        Episode.objects.filter(chapter__story_id=story_id)
        .exclude(maturity=StoryMaturity.PLOT)
        .exists()
    )


def resolve_frontier(progress: AnyStoryProgress) -> None:
    """Set WAITING_FOR_GM or RESTING on a progress that has no way forward.

    Caller is responsible for only invoking this when the player genuinely
    cannot advance (no eligible transition / target below PLOT). Never sets
    COMPLETED — only an explicit staff/owner action does that.
    """
    target = (
        ProgressStatus.WAITING_FOR_GM
        if _story_has_immature_content(progress.story_id)
        else ProgressStatus.RESTING
    )
    if progress.status != target:
        set_progress_status(progress, target)
