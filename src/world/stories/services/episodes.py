"""Episode resolution service for the stories system.

Public API:
    resolve_episode(*, progress, chosen_transition=None, gm_notes="", resolved_by=None)
        — evaluates eligibility, selects or validates the transition, creates an
          EpisodeResolution row, and advances progress.
"""

from typing import Any

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import StoryScope, TransitionMode
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
        2. If empty → raise NoEligibleTransitionError.
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
        6. Return the EpisodeResolution instance.
    """
    eligible = get_eligible_transitions(progress)

    if not eligible:
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

    # Narrative notification — fans out a NarrativeMessage per recipient.
    from world.stories.services.narrative import notify_episode_resolution  # noqa: PLC0415

    notify_episode_resolution(resolution, progress)

    # Internal cascade: any other story's beat with STORY_AT_MILESTONE
    # referencing the advanced story should re-evaluate now. The hook is
    # idempotent and safe to call after commit.
    from world.stories.services.reactivity import on_story_advanced  # noqa: PLC0415

    on_story_advanced(progress.story)

    return resolution
