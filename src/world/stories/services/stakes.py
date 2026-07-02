"""Stakes-contract engine: readiness validation, activation, effective risk.

#1770 PR1. The contract's data model lives in world.stories.models; this
module owns the rules: is the contract complete (readiness), what does it
actually pay for THIS party (effective risk), and the lock lifecycle
(activation -> resolution).
"""

from __future__ import annotations

import logging
from statistics import mean
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from world.societies.constants import RenownRisk
from world.stories.constants import (
    RISK_LADDER,
    BeatOutcome,
    StakeResolutionColumn,
    StakeSeverity,
    StoryMaturity,
)
from world.stories.models import Beat, RiskCalibration, Stake, StakeContractActivation, Transition
from world.stories.types import StakesReadinessReport

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger(__name__)

# Every this-many levels of over-level drops effective risk one tier;
# the same gap under-level raises it, capped at UNDER_LEVEL_MAX_UPGRADE.
# Starting curve per the #1770 spec — designer-tunable by code change only
# deliberately (the ladder shift is an invariant, not content).
LEVELS_PER_TIER = 2
UNDER_LEVEL_MAX_UPGRADE = 1


def risk_index(risk: str) -> int:
    """Position of a RenownRisk value on the weakest->strongest ladder."""
    return RISK_LADDER.index(risk)


def compute_effective_risk(declared_risk: str, target_level: int, party_average_level: int) -> str:
    """What the declared risk is actually worth to this party (#1770 pillar 4).

    'Highly risky to level 4 is not risky at all to level 10 — no chance
    they'd lose, so no stakes.' Over-leveled parties decay toward NONE;
    under-leveled parties get a bounded upgrade. NONE is a fixed point.
    """
    if declared_risk == RenownRisk.NONE:
        return RenownRisk.NONE
    gap = party_average_level - target_level
    if gap >= 0:
        shift = -(gap // LEVELS_PER_TIER)
    else:
        shift = min(UNDER_LEVEL_MAX_UPGRADE, (-gap) // LEVELS_PER_TIER)
    idx = risk_index(declared_risk) + shift
    idx = max(0, min(len(RISK_LADDER) - 1, idx))
    return RISK_LADDER[idx]


def _beat_offers_removal(beat: Beat) -> bool:
    """The chain rule's terminal condition: this beat can remove a character.

    True when the beat wagers a REMOVAL-severity stake, or its failure pool
    contains a character_loss consequence (world.checks.Consequence bool).
    """
    from world.checks.consequence_resolution import resolve_pool_consequences  # noqa: PLC0415

    if beat.stakes.filter(severity=StakeSeverity.REMOVAL).exists():
        return True
    pool = beat.failure_consequences
    if pool is None:
        return False
    return any(c.character_loss for c in resolve_pool_consequences(pool))


def _transition_follows_failure(transition: Transition, episode_id: int) -> bool:
    """Whether a transition is part of the failure cascade from this episode.

    A transition with no required outcome on any of this episode's beats is
    unconditioned (follows both columns); otherwise it must require FAILURE
    on at least one of them. A stake-level requirement (#1770 PR2) counts as
    failure-following iff it requires the LOSS column.
    """
    reqs = [r for r in transition.cached_required_outcomes if r.beat.episode_id == episode_id]
    if not reqs:
        return True
    return any(
        (r.required_stake_column == StakeResolutionColumn.LOSS)
        if r.stake_id is not None
        else (r.required_outcome == BeatOutcome.FAILURE)
        for r in reqs
    )


def _jeopardy_reachable(beat: Beat, max_hops: int) -> bool:
    """BFS the failure cascade up to max_hops episode-edges (#1770 pillar 3).

    Hop 0 is the beat itself. Downstream episodes count only at OUTLINE or
    PLOT maturity — a PITCH node is an idea, not an authored branch. Bounded
    by max_fuse_hops (<= 3 in the seeded calibration), so the per-episode
    queries stay small; revisit with a prefetch if calibration ever grows.
    """
    if _beat_offers_removal(beat):
        return True
    frontier: set[int] = {beat.episode_id}
    visited: set[int] = set()
    for _hop in range(max_hops):
        next_frontier: set[int] = set()
        for episode_id in frontier - visited:
            visited.add(episode_id)
            transitions = Transition.objects.filter(source_episode_id=episode_id).select_related(
                "target_episode"
            )
            for transition in transitions:
                target = transition.target_episode
                if target is None or target.maturity == StoryMaturity.PITCH:
                    continue
                if not _transition_follows_failure(transition, episode_id):
                    continue
                if any(_beat_offers_removal(downstream) for downstream in target.beats.all()):
                    return True
                next_frontier.add(target.pk)
        frontier = next_frontier
        if not frontier:
            break
    return False


def _stake_column_problems(stakes: list[Stake]) -> list[str]:
    """Every stake must be authored for both the WIN and LOSS columns."""
    problems: list[str] = []
    for stake in stakes:
        columns = {r.column for r in stake.prefetched_resolutions}
        problems.extend(
            f"stake {stake.pk} has no {required} resolution"
            for required in (StakeResolutionColumn.WIN, StakeResolutionColumn.LOSS)
            if required not in columns
        )
    return problems


def _calibration_band_problems(
    beat: Beat, calibration: RiskCalibration, stakes: list[Stake]
) -> list[str]:
    """Total/ceiling severity bands plus the jeopardy-reachability fuse walk."""
    problems: list[str] = []
    total = sum(stake.severity for stake in stakes)
    if total < calibration.severity_floor_total:
        problems.append(
            f"total severity {total} is under the "
            f"{beat.risk} floor {calibration.severity_floor_total}"
        )
    worst = max(stake.severity for stake in stakes)
    if worst > calibration.severity_ceiling:
        problems.append(
            f"a stake at severity {worst} exceeds the "
            f"{beat.risk} ceiling {calibration.severity_ceiling}"
        )
    if not _jeopardy_reachable(beat, calibration.max_fuse_hops):
        problems.append(
            f"removal-from-play is not reachable within {calibration.max_fuse_hops} failure hop(s)"
        )
    return problems


def validate_stakes_readiness(beat: Beat) -> StakesReadinessReport:
    """Is this beat's contract complete enough to run at its declared risk?

    Unready never blocks play (#1770 pillar 7) — activation downgrades
    effective risk to NONE instead. Rules: target_level declared; >=1 stake;
    every stake authored for WIN and LOSS; severity within the tier's
    calibration bands; removal-from-play reachable within max_fuse_hops.
    """
    if beat.risk == RenownRisk.NONE:
        return StakesReadinessReport(is_staked=False, is_ready=True)

    problems: list[str] = []
    if not beat.target_level:
        problems.append("target_level is not declared")

    calibration = RiskCalibration.objects.filter(risk=beat.risk).first()
    if calibration is None:
        problems.append(f"no RiskCalibration row for risk {beat.risk!r}")

    stakes = list(
        beat.stakes.prefetch_related(Prefetch("resolutions", to_attr="prefetched_resolutions"))
    )
    if not stakes:
        problems.append("no stakes declared")
    problems.extend(_stake_column_problems(stakes))

    if calibration is not None and stakes:
        problems.extend(_calibration_band_problems(beat, calibration, stakes))

    return StakesReadinessReport(is_staked=True, is_ready=not problems, problems=tuple(problems))


def get_open_activation(beat: Beat) -> StakeContractActivation | None:
    """The single open (unresolved) activation for this beat, if any."""
    return beat.stake_activations.filter(resolved_at__isnull=True).first()


def activate_stakes_contract(
    beat: Beat, participants: Sequence[CharacterSheet]
) -> StakeContractActivation:
    """Lock the contract at scene start and price it for this party.

    Idempotent while open: a second activation attempt (e.g. two encounter
    starts racing) returns the existing open row unchanged. Unready contracts
    activate at effective NONE — the scene runs, nothing pays (#1770 pillar 7).
    The idempotency check-then-create has a race window; the partial unique
    constraint `unique_open_activation_per_beat` is the real backstop, and a
    losing concurrent create re-fetches and returns the winner's row instead
    of raising.
    """
    from world.stories.services.beats import _character_level  # noqa: PLC0415

    if not participants:
        msg = f"activate_stakes_contract(beat={beat.pk}): participants must be non-empty"
        raise ValueError(msg)

    existing = get_open_activation(beat)
    if existing is not None:
        return existing

    report = validate_stakes_readiness(beat)
    party_average = round(mean(_character_level(sheet) for sheet in participants))
    target = beat.target_level or 0
    if report.is_staked and report.is_ready:
        effective = compute_effective_risk(beat.risk, target, party_average)
    else:
        effective = RenownRisk.NONE
    try:
        with transaction.atomic():
            activation = StakeContractActivation.objects.create(
                beat=beat,
                party_average_level=party_average,
                declared_target_level=target,
                declared_risk=beat.risk,
                effective_risk=effective,
                is_ready=report.is_ready,
                readiness_notes="; ".join(report.problems),
            )
    except IntegrityError:
        activation = get_open_activation(beat)
        if activation is None:
            raise
        return activation
    if report.is_staked and not report.is_ready:
        logger.warning(
            "Stakes contract on beat %s activated UNREADY (effective NONE): %s",
            beat.pk,
            activation.readiness_notes,
        )
    return activation


def effective_risk_for_beat(beat: Beat) -> str:
    """Risk value Legend should pay on: open activation's effective risk,
    else the declared Beat.risk (paths with no activation keep old behavior)."""
    activation = get_open_activation(beat)
    return activation.effective_risk if activation is not None else beat.risk


def resolve_open_activation(beat: Beat) -> None:
    """Close the open activation (if any) — called by the completion tail."""
    activation = get_open_activation(beat)
    if activation is not None:
        activation.resolved_at = timezone.now()
        activation.save(update_fields=["resolved_at"])
