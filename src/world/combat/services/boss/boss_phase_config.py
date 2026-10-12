"""Authored boss phase cloning and break-bar configuration."""

from __future__ import annotations

from decimal import Decimal

from world.combat.constants import BAR_UNITS_PER_ROUND, PACING_FLOOR_ROUND_PADDING
from world.combat.models import BossPhase, CombatEncounter, CombatOpponent, CreatureTemplate


def _clone_authored_phases(
    encounter: CombatEncounter,
    opp: CombatOpponent,
    template: CreatureTemplate,
) -> None:
    """Clone CreaturePhaseTemplate rows into BossPhase rows and stamp break-bar config."""
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415
    from world.combat.scaling import (  # noqa: PLC0415
        compute_party_multiplier,
        compute_party_profile,
    )

    phase_templates = CreaturePhaseTemplate.objects.filter(creature_template=template).order_by(
        "phase_number"
    )
    BossPhase.objects.filter(opponent=opp).delete()

    profile = compute_party_profile(encounter)
    party_mult = compute_party_multiplier(profile.party_size, profile.avg_level)

    for pt in phase_templates:
        phase = BossPhase.objects.create(
            opponent=opp,
            phase_number=pt.phase_number,
            threat_pool=pt.threat_pool,
            soak_value=pt.soak_value,
            probing_threshold=pt.probing_threshold,
            health_trigger_percentage=pt.health_trigger_percentage,
            description=pt.description,
            actions_per_round=pt.actions_per_round,
            damage_multiplier=pt.damage_multiplier,
            extra_actions=pt.extra_actions,
            reinforcement_template=pt.reinforcement_template,
            reinforcement_count=pt.reinforcement_count,
        )
        if hasattr(pt, "break_bar"):
            _stamp_phase_break_bar_config(phase, pt.break_bar, party_mult, opp, pt.phase_number)


def minimum_break_bar_threshold() -> int:
    """Pacing floor for a boss's break-bar threshold (#2642, batch-3 F-7a).

    ``(soulfray_stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND`` —
    ensures the anima -> Soulfray -> audere arc has room to play out before the
    wall breaks (median 6-8 rounds, tail ~10). Returns 0 (no clamp) when Soulfray
    has not been authored yet (stage_count == 0) — a bare/test DB should not be
    forced onto a floor derived from unauthored content.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    stage_count = ConditionStage.objects.filter(condition__name=SOULFRAY_CONDITION_NAME).count()
    if stage_count == 0:
        return 0
    return (stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND


def _stamp_phase_break_bar_config(
    phase: BossPhase,
    config: object,
    party_mult: Decimal,
    opp: CombatOpponent,
    phase_number: int,
) -> None:
    """Stamp BreakBarConfig values onto a BossPhase (and onto the opponent for phase 1)."""
    authored_threshold = round(Decimal(config.max_threshold) * party_mult)
    threshold = max(authored_threshold, minimum_break_bar_threshold())
    phase.break_bar_threshold = threshold
    phase.vulnerability_rounds = config.vulnerability_rounds
    phase.vulnerability_intensity_bonus = config.intensity_bonus
    phase.save(
        update_fields=[
            "break_bar_threshold",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
        ]
    )
    if phase_number == 1:
        opp.break_bar_threshold = threshold
        opp.break_bar_current = threshold
        opp.vulnerability_rounds = config.vulnerability_rounds
        opp.vulnerability_intensity_bonus = config.intensity_bonus
        opp.save(
            update_fields=[
                "break_bar_threshold",
                "break_bar_current",
                "vulnerability_rounds",
                "vulnerability_intensity_bonus",
            ]
        )
