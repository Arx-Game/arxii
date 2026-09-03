"""Episode resolution service for the stories system.

Public API:
    resolve_episode(*, progress, gm_notes="", resolved_by=None)
        - evaluates eligibility, selects the transition, creates an
          EpisodeResolution row, and advances progress.
"""

from typing import Any

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import StoryMaturity, StoryScope
from world.stories.exceptions import NoEligibleTransitionError
from world.stories.models import EpisodeResolution, Era, Transition
from world.stories.services.progress import advance_progress_to_episode
from world.stories.services.transitions import get_eligible_transitions
from world.stories.types import AnyStoryProgress


def _select_transition(progress: AnyStoryProgress) -> Transition:
    """The transition that fires now: the lowest (order, pk) eligible edge.

    Zero eligible edges: a genuine frontier (no outbound transitions) resolves
    through resolve_frontier; otherwise NoEligibleTransitionError. Several
    eligible edges resolve by authored order (#3565): routing is decided when
    the episode is written, never by a GM after the players act.
    """
    eligible = get_eligible_transitions(progress)
    if not eligible:
        if not progress.current_episode.outbound_transitions.exists():
            from world.stories.services.frontier import resolve_frontier  # noqa: PLC0415

            resolve_frontier(progress)
        raise NoEligibleTransitionError
    return eligible[0]  # get_eligible_transitions orders by (order, pk)


def resolve_episode(
    *,
    progress: AnyStoryProgress,
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
        3. Otherwise the lowest (order, pk) eligible transition fires (#3565):
           routing is decided by the author, never by a GM after the fact.
        4. Atomically:
               a. Create EpisodeResolution, populating the scope-appropriate FK:
                  - CHARACTER → character_sheet
                  - GROUP     → gm_table
                  - GLOBAL    → both null
               b. Advance progress.current_episode to transition.target_episode (may be None).
           Then reconcile status: a non-PLOT target routes through
           resolve_frontier (not runnable yet); a PLOT target restores
           ACTIVE if a stale frontier status was set; a None target is
           left untouched (documented follow-up).
        5. Return the EpisodeResolution instance.
    """
    selected = _select_transition(progress)

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

    # Stamp GM activity (#2004) — the resolution succeeded.
    if resolved_by is not None:
        from world.gm.models import GMRewardConfig  # noqa: PLC0415
        from world.gm.services import touch_gm_activity  # noqa: PLC0415
        from world.stories.services.gm_rewards import credit_gm_story_reward  # noqa: PLC0415

        touch_gm_activity(resolved_by)

        # Credit GM Story Reward XP (#2123) — same scope-derived anchor used
        # to build resolution_kwargs above.
        reward_character_sheet = progress.character_sheet if scope == StoryScope.CHARACTER else None
        reward_gm_table = progress.gm_table if scope == StoryScope.GROUP else None
        config = GMRewardConfig.load()
        credit_gm_story_reward(
            resolved_by=resolved_by,
            scope=scope,
            character_sheet=reward_character_sheet,
            gm_table=reward_gm_table,
            per_player_xp=config.episode_xp_per_player,
            event_cap=config.episode_xp_cap,
            label=f"episode '{episode.title}' resolved",
        )

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
