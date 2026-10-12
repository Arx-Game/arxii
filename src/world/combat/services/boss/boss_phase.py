"""Boss phase advancement and its stamped effects."""

from __future__ import annotations

from decimal import Decimal

from world.combat.models import BossPhase, CombatOpponent
from world.combat.services.boss.boss_phase_config import minimum_break_bar_threshold
from world.combat.services.boss.phase_narration import _narrate_phase_transition
from world.combat.services.boss.reinforcements import _spawn_reinforcements

# ---------------------------------------------------------------------------
# Boss phase transitions
# ---------------------------------------------------------------------------


def check_and_advance_boss_phase(
    opponent: CombatOpponent,
) -> BossPhase | None:
    """Check whether a boss should advance to the next phase and apply it.

    Transition happens when the boss's health drops to or below a phase's
    ``health_trigger_percentage``. The next phase (by ``phase_number``) whose
    trigger is satisfied and whose ``phase_number`` is greater than the
    opponent's ``current_phase`` is activated.

    On transition:
    - ``opponent.current_phase`` advances.
    - ``threat_pool``, ``soak_value`` are swapped from the new phase.
    - ``probing_current`` is reset to zero.
    - If the new phase has a ``probing_threshold``, it overwrites the
      opponent's ``probing_threshold``.
    - A dramatic surge fires for every ACTIVE PC (#3445): BOSS_ENRAGE when the
      phase raises damage_multiplier, else BOSS_PHASE.
    - The room is told (#3552): the phase's authored ``description`` when set,
      else a generic shift line; an enraging transition adds an enrage line.
      Not curve-gated, unlike the surge.

    Args:
        opponent: The boss opponent to check.

    Returns:
        The ``BossPhase`` that was activated, or ``None`` if no transition.
    """
    phases = list(
        BossPhase.objects.filter(
            opponent=opponent,
            phase_number__gt=opponent.current_phase,
        ).order_by("phase_number")
    )

    health_pct = opponent.health_percentage
    previous_multiplier = opponent.damage_multiplier

    for phase in phases:
        if phase.health_trigger_percentage is None:
            continue
        if health_pct <= phase.health_trigger_percentage:
            _apply_phase_transition(opponent, phase)
            _spawn_reinforcements(opponent.encounter, phase)
            _surge_on_phase_transition(opponent, phase, previous_multiplier)
            _narrate_phase_transition(
                opponent, phase, enraged=phase.damage_multiplier > previous_multiplier
            )
            return phase

    return None


def _surge_on_phase_transition(
    opponent: CombatOpponent,
    phase: BossPhase,
    previous_multiplier: Decimal,
) -> None:
    """Fire the boss-beat surge for a transition that just landed (#3445).

    The beat is BOSS_ENRAGE when the new phase makes the boss hit harder and
    BOSS_PHASE otherwise - mutually exclusive, so one transition is one surge.
    A phase that only grants ``extra_actions`` is a plain phase beat, per the
    issue's ratified decision 1.
    """
    from world.combat.escalation import apply_boss_phase_surge  # noqa: PLC0415

    apply_boss_phase_surge(
        opponent=opponent,
        enraged=phase.damage_multiplier > previous_multiplier,
    )


def _apply_phase_transition(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp all phase-sourced fields onto the opponent and save."""
    opponent.current_phase = phase.phase_number
    if phase.threat_pool_id:
        opponent.threat_pool = phase.threat_pool
    opponent.soak_value = phase.soak_value
    opponent.probing_current = 0
    if phase.probing_threshold is not None:
        opponent.probing_threshold = phase.probing_threshold
    _stamp_enrage(opponent, phase)
    _stamp_break_bar(opponent, phase)
    opponent.save(
        update_fields=[
            "current_phase",
            "threat_pool_id",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "damage_multiplier",
            "actions_per_round",
            "break_bar_threshold",
            "break_bar_current",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
            "vulnerability_rounds_remaining",
        ],
    )


def _stamp_enrage(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp damage multiplier and actions_per_round from phase config."""
    opponent.damage_multiplier = phase.damage_multiplier
    if phase.actions_per_round is not None:
        opponent.actions_per_round = phase.actions_per_round + phase.extra_actions
    else:
        opponent.actions_per_round = opponent.actions_per_round + phase.extra_actions


def _stamp_break_bar(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Reset the break bar from the new phase's break-bar config.

    Re-applies the pacing floor (#2642) on top of the phase's authored
    threshold — ``_stamp_phase_break_bar_config`` already clamps it at clone
    time, but this keeps the invariant self-evident at the site that actually
    writes the opponent's live ``break_bar_threshold`` on a phase transition.
    """
    if phase.break_bar_threshold > 0:
        threshold = max(phase.break_bar_threshold, minimum_break_bar_threshold())
        opponent.break_bar_threshold = threshold
        opponent.break_bar_current = threshold
        opponent.vulnerability_rounds = phase.vulnerability_rounds
        opponent.vulnerability_intensity_bonus = phase.vulnerability_intensity_bonus
        opponent.vulnerability_rounds_remaining = 0
    else:
        opponent.break_bar_threshold = 0
        opponent.break_bar_current = 0
        opponent.vulnerability_rounds_remaining = 0
