"""Selecting targets for NPC and opponent actions."""

from __future__ import annotations

from collections.abc import Callable
import random
from typing import TYPE_CHECKING, TypeVar

from world.combat.constants import TargetingMode, TargetSelection
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    ThreatPoolEntry,
)
from world.combat.services.declarations.hostility import combatants_hostile_to
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    pass


def _get_eligible_entries(
    opponent: CombatOpponent,
    entries: list[ThreatPoolEntry],
    cooldown_used_entry_ids: set[int],
) -> list[ThreatPoolEntry]:
    """Return threat pool entries eligible for this opponent's current state.

    Args:
        opponent: The opponent selecting an action.
        entries: Pre-fetched threat pool entries for this opponent's pool.
        cooldown_used_entry_ids: Entry IDs recently used (within cooldown window)
            by this opponent. Pre-fetched in batch by the caller.
    """
    eligible: list[ThreatPoolEntry] = []
    # Falter: skip entries that require a steady nerve (#2015).
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    faltering = morale_state_for(opponent) == OpponentMoraleState.FALTER

    for entry in entries:
        # Falter: skip requires_steady entries (designers author "weakened" entries).
        if faltering and entry.requires_steady:
            continue

        # Filter by minimum_phase
        if entry.minimum_phase is not None and entry.minimum_phase > opponent.current_phase:
            continue

        # Filter by cooldown — check against pre-fetched set
        if entry.cooldown_rounds is not None and entry.pk in cooldown_used_entry_ids:
            continue

        eligible.append(entry)

    return eligible


_TargetT = TypeVar("_TargetT")


def _select_targets_core(
    entry: ThreatPoolEntry,
    candidates: list[_TargetT],
    health_of: Callable[[list[_TargetT]], list[int]],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[_TargetT]:
    """Shared targeting-mode selector for participants and opponents (#1584).

    One algorithm (ALL / MULTI / RANDOM / LOWEST_HEALTH / HIGHEST_THREAT /
    SPECIFIC_ROLE / rotated-default) drives both the participant ``targets``
    path and the opponent ``opponent_targets`` path (ADR-0016 — no parallel
    selector).

    ``health_of`` returns health values parallel to ``candidates`` and is only
    invoked for the LOWEST_HEALTH mode, so participants keep their single batch
    query and opponents read ``.health`` directly.

    ``_threat_map`` and ``_shield_participant_ids`` are pre-computed by
    ``select_npc_actions`` for HIGHEST_THREAT / SPECIFIC_ROLE modes (#2020).
    They map candidate PKs to threat values and identify SHIELD-axis PCs (blend
    weight > 0).

    ``rotation`` offsets the deterministic (non-random, non-health-sorted)
    selection so a swarm's successive attacks fan across distinct targets rather
    than dogpiling the first one (#983). It is a no-op for the ALL, RANDOM, and
    LOWEST_HEALTH modes, which already spread across or intentionally focus on
    their own terms.
    """
    if not candidates:
        return []

    mode = entry.targeting_mode
    selection = entry.target_selection

    if mode == TargetingMode.ALL:
        return list(candidates)

    count = 1
    if mode == TargetingMode.MULTI:
        count = entry.target_count or 1

    count = min(count, len(candidates))

    if selection == TargetSelection.LOWEST_HEALTH:
        healths = health_of(candidates)
        sorted_by_health = [
            c
            for _, c in sorted(
                zip(healths, candidates, strict=True),
                key=lambda pair: pair[0],
            )
        ]
        return sorted_by_health[:count]

    if selection == TargetSelection.RANDOM:
        return random.sample(candidates, count)  # NOSONAR game RNG (combat targeting), not crypto

    # HIGHEST_THREAT: sort candidates by ThreatRecord.threat_value desc (#2020).
    # Falls back to rotated order when no threat records exist (pre-threat
    # encounters or mooks with no damage yet).
    if selection == TargetSelection.HIGHEST_THREAT and _threat_map:
        sorted_by_threat = sorted(
            candidates,
            key=lambda c: _threat_map.get(c.pk, 0),
            reverse=True,
        )
        return sorted_by_threat[:count]

    # SPECIFIC_ROLE: prioritize SHIELD-axis (defense) PCs, then break ties
    # by highest threat (#2020). Falls back to highest-threat-only (or rotated)
    # when no SHIELD-axis PC is present.
    if selection == TargetSelection.SPECIFIC_ROLE and _shield_participant_ids:
        shielded = [c for c in candidates if c.pk in _shield_participant_ids]
        if shielded:
            if _threat_map:
                shielded.sort(
                    key=lambda c: _threat_map.get(c.pk, 0),
                    reverse=True,
                )
            return shielded[:count]

    # Default: rotated DB order (no threat data available).
    offset = rotation % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return list(rotated[:count])


def _select_targets(
    entry: ThreatPoolEntry,
    active_participants: list[CombatParticipant],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatParticipant]:
    """Select participant targets for a threat pool entry (typed wrapper)."""

    def _participant_healths(candidates: list[CombatParticipant]) -> list[int]:
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        sheet_ids = [p.character_sheet_id for p in candidates]
        health_map = dict(
            CharacterVitals.objects.filter(
                character_sheet_id__in=sheet_ids,
            ).values_list("character_sheet_id", "health")
        )
        return [health_map.get(p.character_sheet_id, 0) for p in candidates]

    return _select_targets_core(
        entry,
        active_participants,
        _participant_healths,
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _select_opponent_targets(
    entry: ThreatPoolEntry,
    active_opponents: list[CombatOpponent],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatOpponent]:
    """Select opponent targets for a threat pool entry (typed wrapper, #1584).

    Routes an ALLY summon's attack at ENEMY opponents; opponents carry health on
    the row, so no batch query is needed.
    """
    return _select_targets_core(
        entry,
        active_opponents,
        lambda opps: [o.health for o in opps],
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _targetable_participants(encounter: CombatEncounter) -> list[CombatParticipant]:
    """The PCs an NPC may pick as a target this round.

    Design: NPCs target PCs who can still act (not dead, not incapacitated).
    Unconscious PCs (awareness 0) are "down" and not picked as targets; a
    dying-but-conscious PC remains in the fight and is targetable. can_act is
    the same coarse agency gate used for declaration eligibility.
    Intangible PCs (incorporeal, sunk, phased) are also excluded (#1584 Task 8).
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.conditions.services import is_untargetable  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    candidates = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    return [
        p
        for p in candidates
        if can_act(p.character_sheet) and not is_untargetable(p.character_sheet.character)
    ]


def _npc_action_target_pool(
    opponent: CombatOpponent,
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,  # noqa: ARG001 - kept for caller signature symmetry
    *,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> tuple[list, bool]:
    """Route an opponent's targeting by EFFECTIVE allegiance (#1584, #1590, #4091).

    * **ALLY_OF_CASTER** (a #1584 ALLY summon, or a charmed NPC) targets
      ``combatants_hostile_to``'s opponent pool — ACTIVE opponents whose
      effective allegiance is ENEMY or TURNED — minus untargetable
      (intangible) opponents; never a PC.
    * **TURNED** targets other ACTIVE opponents still on its former
      (stored-ENEMY, effectively ENEMY) side; never a PC, never itself.
    * **NEUTRAL** (calmed) skips the round: empty opponent pool.
    * **ENEMY** (the common case) targets the PC side as today — enemies
      ignore charmed/turned NPCs (Decision 3).

    ``active_participants`` is already intangibility- and can_act-filtered by
    ``select_npc_actions``.

    Returns ``(target_pool, targeting_participants)``.
    """
    side = allegiances.get(opponent.pk, Allegiance.ENEMY)
    if side in (Allegiance.ALLY_OF_CASTER, Allegiance.TURNED):
        from world.conditions.services import is_untargetable  # noqa: PLC0415

        opponent_pool = [
            opp
            for opp in combatants_hostile_to(
                opponent, allegiances=allegiances, opponents=active_opponents
            )["opponents"]
            if opp.objectdb_id is None or not is_untargetable(opp.objectdb)
        ]
        return opponent_pool, False
    if side == Allegiance.NEUTRAL:
        return [], True
    return list(active_participants), True


def _set_npc_action_targets(  # noqa: PLR0913
    action: CombatOpponentAction,
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> None:
    """Populate exactly one target relation on an NPC action (#1584).

    The opponent branch (an ALLY/charmed/turned attacker, #4091) never forwards
    ``threat_map``/``shield_participant_ids`` — both are pre-computed keyed by
    CombatParticipant pk, and a CombatOpponent pk can collide with one of those
    keys (they are independent sequences), silently corrupting HIGHEST_THREAT /
    SPECIFIC_ROLE selection for opponent targets.
    """
    if targeting_participants:
        action.targets.set(
            _select_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=threat_map,
                _shield_participant_ids=shield_participant_ids,
            )
        )
    else:
        action.opponent_targets.set(
            _select_opponent_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=None,
                _shield_participant_ids=None,
            )
        )
