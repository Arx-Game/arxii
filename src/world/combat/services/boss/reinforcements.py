"""Spawning and counting boss reinforcements."""

from __future__ import annotations

from world.combat import services as _svc
from world.combat.constants import EngagementLockStatus, OpponentStatus
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    EngagementLock,
)
from world.combat.services.encounter.behavior_conditions import (
    _has_active_behavior_altering_condition,
)


def _spawn_reinforcements(encounter: CombatEncounter, phase: BossPhase) -> None:
    """Spawn reinforcement adds on phase entry."""
    if phase.reinforcement_template_id is None or phase.reinforcement_count <= 0:
        return
    for _ in range(phase.reinforcement_count):
        _svc.add_opponent(
            encounter,
            name=phase.reinforcement_template.name,
            tier=phase.reinforcement_template.tier,
            threat_pool=phase.reinforcement_template.threat_pool,
            max_health=20,
            auto_phases=False,
        )


def _active_reinforcer_count(boss: CombatOpponent, round_number: int) -> int:
    """Count *boss*'s active, unsuppressed, acting lieutenants this round (the gate divisor, #2642).

    Active = ``OpponentStatus.ACTIVE``, morale not BREAK, no behavior-altering
    condition on the lieutenant's ObjectDB, not pinned in an ACTIVE
    ``EngagementLock``, and it acted this round (has a ``CombatOpponentAction``
    row). A parked/idle lieutenant does not gate.
    """
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss, status=OpponentStatus.ACTIVE))
    if not lieutenants:
        return 0

    acted_ids = set(
        CombatOpponentAction.objects.filter(
            opponent__in=lieutenants,
            round_number=round_number,
        ).values_list("opponent_id", flat=True)
    )

    count = 0
    for lieutenant in lieutenants:
        if lieutenant.pk not in acted_ids:
            continue
        if morale_state_for(lieutenant) == OpponentMoraleState.BREAK:
            continue
        if lieutenant.objectdb_id is not None and _has_active_behavior_altering_condition(
            lieutenant.objectdb_id
        ):
            continue
        if EngagementLock.objects.filter(
            opponent=lieutenant, status=EngagementLockStatus.ACTIVE
        ).exists():
            continue
        count += 1
    return count
