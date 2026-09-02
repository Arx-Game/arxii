"""Transition eligibility service for the stories system.

Public API:
    get_eligible_transitions(progress) — returns the transitions from the
        current episode whose progression requirements AND routing predicates
        are all satisfied.
    validate_routing_readiness(episode) — reports outbound transition pairs
        whose requirement sets never contradict (#3565): an authoring-time
        warning, since the lowest (order, pk) fires silently at runtime.
"""

from django.db.models import Prefetch

from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.models import Episode, Transition, TransitionRequiredOutcome
from world.stories.types import AnyStoryProgress, RoutingReadinessReport


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
    # Prefetch routing requirements with beats (and stakes, for stake-level
    # routing — #1770 PR2); populate cached_required_outcomes.
    routing_prefetch = Prefetch(
        "required_outcomes",
        queryset=TransitionRequiredOutcome.objects.select_related("beat", "stake"),
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
    """Lazily expire overdue beats scoped to a single episode (#3558: a real completion).

    Called at the top of get_eligible_transitions so that eligibility checks
    reflect current deadline state even if no global cron has fired.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.stories.constants import BeatOutcome  # noqa: PLC0415
    from world.stories.services.beats import _expire_each  # noqa: PLC0415

    now = timezone.now()
    overdue = episode.beats.filter(
        outcome=BeatOutcome.UNSATISFIED,
        deadline__isnull=False,
        deadline__lt=now,
    )
    _expire_each(list(overdue), now=now)


def _routing_satisfied(routing_reqs: list[TransitionRequiredOutcome]) -> bool:
    """Return True if all routing requirements are met.

    An empty requirement set is unconditionally satisfied (the transition has
    no routing predicate, so it fires whenever progression requirements pass).
    """
    return all(_routing_req_met(req) for req in routing_reqs)


def _routing_req_met(req: TransitionRequiredOutcome) -> bool:
    """Whether one routing requirement is currently satisfied.

    Stake-level requirement (#1770 PR2): satisfied iff the stake's single
    StakeOutcome (unique per stake) has the required column — one beat's
    stakes can route to different downstream episodes. Routing sets are tiny
    (a handful of rows per transition), so the outcome lookup is a deliberate
    small query per stake-level requirement rather than an extra prefetch
    layer.

    Beat-level requirement: the beat's coarse outcome, unchanged.
    """
    if req.stake_id is not None:
        # Direct table query — the related manager's prefetched cache on an
        # idmapper-shared Stake instance can be stale.
        from world.stories.models import StakeOutcome  # noqa: PLC0415

        outcome = StakeOutcome.objects.filter(stake_id=req.stake_id).first()
        return outcome is not None and outcome.column == req.required_stake_column
    if req.beat.outcome != req.required_outcome:
        return False
    return not req.required_outcome_key or req.beat.outcome_key == req.required_outcome_key


def validate_routing_readiness(episode: Episode) -> RoutingReadinessReport:
    """Report every pair of outbound transitions whose requirement sets never contradict.

    Two transitions are ambiguous when no beat or stake they both constrain is
    constrained to different values (an unconstrained pair is ambiguous). The
    lowest (order, pk) would fire, which is a silent authoring mistake, so the
    author tree surfaces it.
    """
    readiness_prefetch = Prefetch(
        "required_outcomes",
        queryset=TransitionRequiredOutcome.objects.all(),
        to_attr="cached_routing_reqs_for_readiness",
    )
    transitions = list(
        episode.outbound_transitions.prefetch_related(readiness_prefetch).order_by("order", "pk")
    )
    pairs: list[tuple[int, int]] = [
        (first.pk, second.pk)
        for i, first in enumerate(transitions)
        for second in transitions[i + 1 :]
        if not _contradict(
            first.cached_routing_reqs_for_readiness, second.cached_routing_reqs_for_readiness
        )
    ]
    return RoutingReadinessReport(ambiguous_pairs=tuple(pairs))


def _contradict(
    rows_a: list[TransitionRequiredOutcome], rows_b: list[TransitionRequiredOutcome]
) -> bool:
    """True when some shared subject (beat or stake) is required to differ."""
    by_beat_a = {
        r.beat_id: (r.required_outcome, r.required_outcome_key)
        for r in rows_a
        if r.stake_id is None
    }
    by_beat_b = {
        r.beat_id: (r.required_outcome, r.required_outcome_key)
        for r in rows_b
        if r.stake_id is None
    }
    for beat_id, (outcome_a, key_a) in by_beat_a.items():
        if beat_id not in by_beat_b:
            continue
        outcome_b, key_b = by_beat_b[beat_id]
        if outcome_a != outcome_b:
            return True
        if key_a and key_b and key_a != key_b:
            return True
    by_stake_a = {r.stake_id: r.required_stake_column for r in rows_a if r.stake_id is not None}
    by_stake_b = {r.stake_id: r.required_stake_column for r in rows_b if r.stake_id is not None}
    return any(
        stake_id in by_stake_b and by_stake_b[stake_id] != column
        for stake_id, column in by_stake_a.items()
    )
