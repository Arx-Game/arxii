"""Swarm opponents: attack counts and kills."""

from __future__ import annotations

import math

from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent
from world.combat.types import OpponentDamageResult


def swarm_kills(raw_damage: int, body_toughness: int) -> int:
    """Bodies a single landing attack clears from a swarm (#875).

    A landing hit always clears at least one body; big hits mow through many.
    ``body_toughness`` is the damage needed per body.
    """
    if raw_damage <= 0:
        return 0
    return max(1, raw_damage // max(1, body_toughness))


def swarm_attack_count(swarm_count: int, bodies_per_attack: int, active_pc_count: int) -> int:
    """Attacks a swarm makes this round — scales with remaining bodies (#875).

    Capped at the number of PCs who can act, so a swarm fans across the party
    rather than dogpiling one PC. Derived on read; nothing persisted.
    """
    if swarm_count <= 0 or active_pc_count <= 0:
        return 0
    raw = math.ceil(swarm_count / max(1, bodies_per_attack))
    return max(1, min(raw, active_pc_count))


def _zero_opponent_damage_result(opponent: CombatOpponent) -> OpponentDamageResult:
    """A no-effect damage result (hit cancelled or reduced to nothing)."""
    return OpponentDamageResult(
        damage_dealt=0,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=False,
        kills=0,
        opponent_id=opponent.pk,
    )


def _apply_swarm_damage(opponent: CombatOpponent, raw_damage: int) -> OpponentDamageResult:
    """Resolve a landing hit on a SWARM opponent (#875).

    Swarms have no HP, soak, or probing — a landing attack clears bodies.
    """
    kills = min(swarm_kills(raw_damage, opponent.body_toughness or 1), opponent.swarm_count)
    opponent.swarm_count -= kills
    defeated = opponent.swarm_count <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED
    opponent.save(update_fields=["swarm_count", "status"])
    return OpponentDamageResult(
        damage_dealt=kills,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=defeated,
        kills=kills,
        opponent_id=opponent.pk,
    )
