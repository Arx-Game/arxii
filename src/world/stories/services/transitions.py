"""Transition eligibility service for the stories system.

Public API:
    get_eligible_transitions(progress) — returns the transitions from the
        current episode whose progression requirements AND routing predicates
        are all satisfied.
"""

from django.db.models import Prefetch

from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.models import Episode, Transition, TransitionRequiredOutcome
from world.stories.types import AnyStoryProgress


def get_eligible_transitions(progress: AnyStoryProgress) -> list[Transition]:
    """Return the transitions eligible to fire from the current episode.

    An outbound transition is eligible when:
        1. All EpisodeProgressionRequirements on the current episode are met
           (each gating beat's outcome equals the required_outcome).
        2. All TransitionRequiredOutcomes on the transition are met
           (each routing beat's outcome equals that requirement's required_outcome).
           An empty TransitionRequiredOutcome set is always eligible.

    Returns an empty list when:
        - progress.current_episode is None (frontier or not started)
        - No outbound transitions are authored AND no progression requirements exist
          (frontier pause — the story author has not yet written the next episode)
        - No outbound transition passes its routing predicate check

    Raises:
        ProgressionRequirementNotMetError: when at least one EpisodeProgressionRequirement
            is unmet. Callers that need to distinguish "blocked by unmet gate" from
            "frontier pause (no episodes authored yet)" should catch this exception.

    Ordered by Transition.order, then pk for determinism.
    """
    if progress.current_episode is None:
        return []

    episode = progress.current_episode

    # Lazily expire any overdue beats in the current episode before checking eligibility.
    # This ensures transition routing reflects current deadline state even if no cron has fired.
    _expire_overdue_beats_for_episode(episode)

    # Step 1: Check all EpisodeProgressionRequirements.
    # select_related to avoid N+1 on beat FK.
    progression_reqs = list(episode.progression_requirements.select_related("beat").all())
    for req in progression_reqs:
        if req.beat.outcome != req.required_outcome:
            raise ProgressionRequirementNotMetError

    # Step 2: Evaluate each outbound transition's routing requirements.
    # Prefetch routing requirements with beats; populate cached_required_outcomes.
    routing_prefetch = Prefetch(
        "required_outcomes",
        queryset=TransitionRequiredOutcome.objects.select_related("beat"),
        to_attr="cached_required_outcomes",
    )
    transitions = list(
        episode.outbound_transitions.prefetch_related(routing_prefetch).order_by("order", "pk")
    )

    return [t for t in transitions if _routing_satisfied(t.cached_required_outcomes)]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _expire_overdue_beats_for_episode(episode: Episode) -> None:
    """Lazily expire overdue beats scoped to a single episode.

    Called at the top of get_eligible_transitions so that eligibility checks
    reflect current deadline state even if no global cron has fired.

    Uses .save() (not .update()) to update SharedMemoryModel's identity-map
    cache in place — bulk .update() bypasses the ORM layer and leaves stale
    Python objects in memory, which would break the subsequent FK walks in
    progression_requirements and routing predicates.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.stories.constants import BeatOutcome  # noqa: PLC0415

    now = timezone.now()
    overdue = episode.beats.filter(
        outcome=BeatOutcome.UNSATISFIED,
        deadline__isnull=False,
        deadline__lt=now,
    )
    for beat in overdue:
        beat.outcome = BeatOutcome.EXPIRED
        beat.save(update_fields=["outcome", "updated_at"])


def _routing_satisfied(routing_reqs: list[TransitionRequiredOutcome]) -> bool:
    """Return True if all routing requirements are met.

    An empty requirement set is unconditionally satisfied (the transition has
    no routing predicate, so it fires whenever progression requirements pass).
    """
    return all(req.beat.outcome == req.required_outcome for req in routing_reqs)
