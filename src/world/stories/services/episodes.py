"""Episode resolution service for the stories system.

Public API:
    resolve_episode(*, progress, chosen_transition=None, gm_notes="", resolved_by=None)
        — evaluates eligibility, selects or validates the transition, creates an
          EpisodeResolution row, and advances StoryProgress.
"""

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import TransitionMode
from world.stories.exceptions import AmbiguousTransitionError, NoEligibleTransitionError
from world.stories.models import EpisodeResolution, Era, StoryProgress, Transition
from world.stories.services.transitions import get_eligible_transitions


def resolve_episode(
    *,
    progress: StoryProgress,
    chosen_transition: Transition | None = None,
    gm_notes: str = "",
    resolved_by: GMProfile | None = None,
) -> EpisodeResolution:
    """Resolve the current episode for a story progress record.

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
               a. Create EpisodeResolution (episode, character_sheet, chosen_transition,
                  resolved_by, gm_notes, era).
               b. Advance progress.current_episode to transition.target_episode (may be None).
               c. Save progress with update_fields to trigger last_advanced_at (auto_now=True).
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

    with transaction.atomic():
        resolution = EpisodeResolution.objects.create(
            episode=episode,
            character_sheet=progress.character_sheet,
            chosen_transition=selected,
            resolved_by=resolved_by,
            era=era,
            gm_notes=gm_notes,
        )
        # Advance the progress pointer (target_episode may be None → frontier).
        progress.current_episode = selected.target_episode
        # Saving with update_fields triggers the auto_now=True on last_advanced_at.
        progress.save(update_fields=["current_episode", "last_advanced_at"])

    return resolution
