"""Execute multiplier and opponent health before a hit."""

from __future__ import annotations

from decimal import Decimal

from world.combat.models import CombatOpponent


def _opponent_health_before_pct(opponent: CombatOpponent) -> float:
    """Pre-hit health fraction for an opponent (#2643 execute basis). 0.0 when maxless."""
    if opponent.max_health <= 0:
        return 0.0
    return max(0.0, opponent.health / opponent.max_health)


def _apply_execute_multiplier(
    damage_amount: int, multiplier: Decimal, health_before_pct: float
) -> int:
    """Scale damage up as the target's PRE-hit health runs low (#2643 execute).

    ``factor = 1 + multiplier * missing_health_fraction`` where
    ``missing_health_fraction = 1 - health_before_pct``. A zero (the default on every
    damage profile) or falsy ``multiplier`` is a byte-identical no-op — every existing
    damage test is unaffected. Basis is always PRE-hit health (captured by the caller
    before this hit's own subtraction), so a second hit in the same exchange correctly
    prices off the health the FIRST hit left behind — never a recursive
    self-referential fraction, no matter how many hits land in sequence.
    """
    if not multiplier:
        return damage_amount
    missing_health_fraction = 1.0 - health_before_pct
    factor = 1 + float(multiplier) * missing_health_fraction
    return max(0, int(damage_amount * factor))
