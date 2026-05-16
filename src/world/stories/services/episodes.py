"""Episode resolution service for the stories system.

Public API:
    resolve_episode(*, progress, chosen_transition=None, gm_notes="", resolved_by=None)
        — evaluates eligibility, selects or validates the transition, creates an
          EpisodeResolution row, and advances progress.
"""

from typing import Any

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import StoryMaturity, StoryScope, TransitionMode
from world.stories.exceptions import AmbiguousTransitionError, NoEligibleTransitionError
from world.stories.models import EpisodeResolution, Era, Transition
from world.stories.services.progress import advance_progress_to_episode
from world.stories.services.transitions import get_eligible_transitions
from world.stories.types import AnyStoryProgress


def resolve_episode(
    *,
    progress: AnyStoryProgress,
    chosen_transition: Transition | None = None,
    gm_notes: str = "",
    resolved_by: GMProfile | None = None,
) -> EpisodeResolution:
    """Resolve the current episode for a story progress record.

    Works for CHARACTER, GROUP, and GLOBAL scope progress types.

    Algorithm:
        1. Call get_eligible_transitions(progress).
           - If ProgressionRequirementNotMetError is raised, it propagates to the caller.
        2. If empty → raise NoEligibleTransitionError. Side effect: if the
           current episode has NO outbound transitions at all (a genuine
           authoring frontier), route through resolve_frontier first
           (status → WAITING_FOR_GM / RESTING). If outbound transitions
           exist but none are routable yet (a transient routing block — the
           next step is authored, just not unlocked), status stays ACTIVE
           and only the exception is raised.
        3. If chosen_transition is provided:
               - Must be in the eligible set, else raise NoEligibleTransitionError.
               - Use that transition.
        4. Otherwise (no chosen_transition):
               - If exactly one transition is eligible AND mode == AUTO → fire it.
               - If exactly one eligible AND mode == GM_CHOICE → raise AmbiguousTransitionError.
               - If multiple eligible → raise AmbiguousTransitionError.
        5. Atomically:
               a. Create EpisodeResolution, populating the scope-appropriate FK:
                  - CHARACTER → character_sheet
                  - GROUP     → gm_table
                  - GLOBAL    → both null
               b. Advance progress.current_episode to transition.target_episode (may be None).
           Then reconcile status: a non-PLOT target routes through
           resolve_frontier (not runnable yet); a PLOT target restores
           ACTIVE if a stale frontier status was set; a None target is
           left untouched (documented follow-up).
        6. Return the EpisodeResolution instance.
    """
    # get_eligible_transitions raises ProgressionRequirementNotMetError when a
    # progression gate is unmet — that propagates here untouched (the player is
    # *blocked*, status stays ACTIVE). Reaching the line below means the
    # exception did NOT fire, so an empty list is one of two cases (see below).
    eligible = get_eligible_transitions(progress)

    if not eligible:
        # An empty eligible list is NOT necessarily a frontier:
        # get_eligible_transitions also returns [] when outbound transitions
        # exist but no routing predicate is satisfied yet (a transient block,
        # player mid-episode — NOT an authoring frontier). Only treat the
        # genuine "no onward edges authored at all" case as a frontier and
        # route through resolve_frontier (RESTING / WAITING_FOR_GM). In the
        # routing-block case, status stays ACTIVE. Either way, re-raise so the
        # NoEligibleTransitionError contract (view try/except, callers) is
        # intact.
        from world.stories.services.frontier import resolve_frontier  # noqa: PLC0415

        if not progress.current_episode.outbound_transitions.exists():
            resolve_frontier(progress)
        msg = f"No eligible transitions from episode {progress.current_episode_id!r}."
        raise NoEligibleTransitionError(msg)

    if chosen_transition is not None:
        if chosen_transition not in eligible:
            msg = f"Transition {chosen_transition.pk!r} is not in the eligible set."
            raise NoEligibleTransitionError(msg)
        selected = chosen_transition
    else:
        if len(eligible) > 1:
            msg = f"{len(eligible)} eligible transitions — caller must pass chosen_transition."
            raise AmbiguousTransitionError(msg)
        # Exactly one eligible.
        only = eligible[0]
        if only.mode == TransitionMode.GM_CHOICE:
            msg = (
                f"The single eligible transition {only.pk!r} has mode GM_CHOICE; "
                "caller must pass chosen_transition explicitly."
            )
            raise AmbiguousTransitionError(msg)
        selected = only

    era = Era.objects.get_active()
    episode = progress.current_episode
    scope = progress.story.scope

    resolution_kwargs: dict[str, Any] = {
        "episode": episode,
        "chosen_transition": selected,
        "resolved_by": resolved_by,
        "era": era,
        "gm_notes": gm_notes,
    }
    if scope == StoryScope.CHARACTER:
        resolution_kwargs["character_sheet"] = progress.character_sheet
    elif scope == StoryScope.GROUP:
        resolution_kwargs["gm_table"] = progress.gm_table
    # GLOBAL: both character_sheet and gm_table stay null.

    with transaction.atomic():
        resolution = EpisodeResolution.objects.create(**resolution_kwargs)
        advance_progress_to_episode(progress, selected.target_episode)
        # Reconcile status inside the same atomic block as the advance it
        # reconciles: if this save failed post-commit the advance would be
        # durably committed but the status left stale.
        _reconcile_status_after_advance(progress)

    # Narrative notification — fans out a NarrativeMessage per recipient.
    from world.stories.services.narrative import notify_episode_resolution  # noqa: PLC0415

    notify_episode_resolution(resolution, progress)

    # Internal cascade: any other story's beat with STORY_AT_MILESTONE
    # referencing the advanced story should re-evaluate now. The hook is
    # idempotent and safe to call after commit.
    from world.stories.services.reactivity import on_story_advanced  # noqa: PLC0415

    on_story_advanced(progress.story)

    return resolution


def _reconcile_status_after_advance(progress: AnyStoryProgress) -> None:
    """Reconcile progress.status after a successful episode advance.

    - target exists but is still being authored (PITCH/OUTLINE): the player
      cannot run it yet — route through the frontier (WAITING_FOR_GM /
      RESTING) rather than leaving status ACTIVE.
    - target exists and is PLOT: the story is genuinely moving on, so clear
      any stale frontier status left from an earlier pause. The != ACTIVE
      guard avoids a spurious write / last_advanced_at bump on a normal
      advance that was already ACTIVE.
    - target is None (null-target frontier): left untouched here (documented
      follow-up — out of scope).
    """
    if progress.current_episode is None:
        return

    from world.stories.constants import ProgressStatus  # noqa: PLC0415
    from world.stories.services.frontier import (  # noqa: PLC0415
        resolve_frontier,
        set_progress_status,
    )

    if progress.current_episode.maturity != StoryMaturity.PLOT:
        resolve_frontier(progress)
    elif progress.status != ProgressStatus.ACTIVE:
        set_progress_status(progress, ProgressStatus.ACTIVE)
