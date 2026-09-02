"""Authoring-time routing report (#3563).

Before a session runs, answers two questions about one episode's outbound
transitions from the same ``TransitionRequiredOutcome`` rows that
``get_eligible_transitions`` evaluates:

* Dead ends: is there a failure-shaped outcome (a beat's FAILURE, its EXPIRED
  when it has a deadline, or one of its stakes' LOSS) that no outbound
  transition accepts. At runtime that outcome would pause the run at the
  frontier (``resolve_frontier``) mid-session.
* Ambiguity: could two outbound transitions be eligible at once. The lowest
  ``(order, pk)`` edge silently wins (#3565), so the pair is a likely mistake.

The report is advisory: it never blocks saving, resolving or running. An
episode with no outbound transitions gets an empty report (zero transitions is
the authoring frontier by design, not a dead end).

Public API: ``routing_report``, ``routing_reports_for_episodes``,
``rule_accepts``, ``beat_title``.
"""

from collections import defaultdict
from collections.abc import Iterable

from world.stories.constants import BeatOutcome, StakeResolutionColumn
from world.stories.models import (
    Beat,
    Episode,
    EpisodeProgressionRequirement,
    Stake,
    Transition,
    TransitionRequiredOutcome,
)
from world.stories.types import RoutingReport

BEAT_TITLE_MAX = 60


def beat_title(beat: Beat) -> str:
    """First line of the beat's internal description, capped for labels."""
    first_line = beat.internal_description.strip().splitlines()[:1]
    return first_line[0].strip()[:BEAT_TITLE_MAX] if first_line else ""


def rule_accepts(
    req: TransitionRequiredOutcome,
    beat_outcomes: dict[int, str],
    stake_columns: dict[int, str],
) -> bool:
    """True when ``req`` is confirmed met by a hypothetical, fully-known outcome map.

    A dead-end check pins exactly one subject (one beat or one stake) to the
    failure-shaped outcome under test; every other subject is absent from the
    maps. A rule about an absent subject is not confirmed satisfiable, so it
    does not count as accepting: crediting a transition on an unconfirmed
    subject would let an unrelated rule (say a different stake's column) paper
    over a real dead end. This is closed-world by design, unlike
    ``transitions.routing_requirement_met`` (which reads the live row).
    """
    if req.stake_id is not None:
        return stake_columns.get(req.stake_id) == req.required_stake_column
    return beat_outcomes.get(req.beat_id) == req.required_outcome


def routing_report(episode: Episode) -> RoutingReport:
    return routing_reports_for_episodes([episode.pk])[episode.pk]


def routing_reports_for_episodes(episode_ids: Iterable[int]) -> dict[int, RoutingReport]:
    """One report per episode id, in four queries regardless of how many ids."""
    ids = sorted(set(episode_ids))
    if not ids:
        return {}
    transitions_by_episode: dict[int, list[Transition]] = defaultdict(list)
    all_transitions: list[Transition] = []
    for transition in Transition.objects.filter(source_episode_id__in=ids).order_by("order", "pk"):
        transitions_by_episode[transition.source_episode_id].append(transition)
        all_transitions.append(transition)

    # A plain filtered query, not prefetch_related(..., to_attr=...): the to_attr
    # shortcut decides whether a prefetch already ran via hasattr(instance, to_attr),
    # and SharedMemoryModel's identity map hands back the SAME Python object across
    # unrelated calls in this process, so a second routing_report() for a Transition
    # already seen once would silently reuse the first call's stale rule list instead
    # of re-querying (confirmed by repro; see #3563 task-1-report.md).
    rules_by_transition: dict[int, list[TransitionRequiredOutcome]] = defaultdict(list)
    referenced_stake_ids: set[int] = set()
    transition_ids = [t.pk for t in all_transitions]
    for rule in TransitionRequiredOutcome.objects.filter(
        transition_id__in=transition_ids
    ).select_related("beat", "stake"):
        rules_by_transition[rule.transition_id].append(rule)
        if rule.stake_id is not None:
            referenced_stake_ids.add(rule.stake_id)
    for transition in all_transitions:
        transition.cached_required_outcomes = rules_by_transition.get(transition.pk, [])

    progression_by_episode: dict[int, list[EpisodeProgressionRequirement]] = defaultdict(list)
    for req in EpisodeProgressionRequirement.objects.filter(episode_id__in=ids).select_related(
        "beat"
    ):
        progression_by_episode[req.episode_id].append(req)

    candidates_by_episode = {
        episode_id: _candidate_beats(
            episode_id,
            transitions_by_episode.get(episode_id, []),
            progression_by_episode.get(episode_id, []),
        )
        for episode_id in ids
    }
    candidate_beat_ids = [beat.pk for beats in candidates_by_episode.values() for beat in beats]
    stakes_by_beat: dict[int, list[Stake]] = defaultdict(list)
    for stake in Stake.objects.filter(beat_id__in=candidate_beat_ids).order_by("pk"):
        stakes_by_beat[stake.beat_id].append(stake)

    return {
        episode_id: _build_report(
            transitions_by_episode.get(episode_id, []),
            candidates_by_episode[episode_id],
            stakes_by_beat,
            referenced_stake_ids,
        )
        for episode_id in ids
    }


def _candidate_beats(
    episode_id: int,
    transitions: list[Transition],
    progression_reqs: list[EpisodeProgressionRequirement],
) -> list[Beat]:
    """This episode's beats that any progression or routing rule references."""
    seen: dict[int, Beat] = {}
    for req in progression_reqs:
        if req.beat.episode_id == episode_id:
            seen.setdefault(req.beat_id, req.beat)
    for transition in transitions:
        for rule in transition.cached_required_outcomes:
            if rule.beat.episode_id == episode_id:
                seen.setdefault(rule.beat_id, rule.beat)
    return sorted(seen.values(), key=lambda beat: beat.pk)


def _build_report(
    transitions: list[Transition],
    candidate_beats: list[Beat],
    stakes_by_beat: dict[int, list[Stake]],
    referenced_stake_ids: set[int],
) -> RoutingReport:
    if not transitions:
        return RoutingReport()
    dead_ends = _dead_end_lines(transitions, candidate_beats, stakes_by_beat, referenced_stake_ids)
    pairs = [
        (first.pk, second.pk)
        for i, first in enumerate(transitions)
        for second in transitions[i + 1 :]
        if not _contradict(first.cached_required_outcomes, second.cached_required_outcomes)
    ]
    ambiguities = [
        f"transitions #{a} and #{b} could both be eligible at once; #{a} fires first"
        for a, b in pairs
    ]
    return RoutingReport(
        dead_ends=tuple(dead_ends),
        ambiguities=tuple(ambiguities),
        ambiguous_pairs=tuple(pairs),
    )


def _beat_label(beat: Beat) -> str:
    title = beat_title(beat)
    return f"beat #{beat.pk} ({title})" if title else f"beat #{beat.pk}"


def _any_transition_accepts(
    transitions: list[Transition],
    beat_outcomes: dict[int, str],
    stake_columns: dict[int, str],
) -> bool:
    return any(
        all(rule_accepts(rule, beat_outcomes, stake_columns) for rule in t.cached_required_outcomes)
        for t in transitions
    )


def _dead_end_lines(
    transitions: list[Transition],
    candidate_beats: list[Beat],
    stakes_by_beat: dict[int, list[Stake]],
    referenced_stake_ids: set[int],
) -> list[str]:
    lines: list[str] = []
    for beat in candidate_beats:
        outcomes = [BeatOutcome.FAILURE]
        if beat.deadline is not None:
            outcomes.append(BeatOutcome.EXPIRED)
        lines.extend(
            f"{_beat_label(beat)} = {outcome.value.upper()}: no transition accepts it"
            for outcome in outcomes
            if not _any_transition_accepts(transitions, {beat.pk: outcome}, {})
        )
        # A stake with no routing rule referencing it plays no part in routing
        # at all, so its resolution can never strand the run - skip it rather
        # than flag a false dead end (its beat's own coverage is what matters).
        for stake in stakes_by_beat.get(beat.pk, []):
            if stake.pk not in referenced_stake_ids:
                continue
            pinned = {stake.pk: StakeResolutionColumn.LOSS}
            if not _any_transition_accepts(transitions, {}, pinned):
                lines.append(
                    f"stake #{stake.pk} on {_beat_label(beat)} = LOSS: no transition accepts it"
                )
    return lines


def _contradict(
    rows_a: list[TransitionRequiredOutcome],
    rows_b: list[TransitionRequiredOutcome],
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
