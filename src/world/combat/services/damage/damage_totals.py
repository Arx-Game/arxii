"""Round damage totals for opponents."""

from __future__ import annotations

from world.combat.types import ActionOutcome, OpponentDamageResult


def _opponent_damage_totals(outcome: ActionOutcome) -> dict[int, int]:
    """Aggregate only opponent damage, including repeated hits on the same opponent."""
    damage: dict[int, int] = {}
    for dealt in outcome.damage_results:
        if isinstance(dealt, OpponentDamageResult) and dealt.opponent_id is not None:
            damage[dealt.opponent_id] = damage.get(dealt.opponent_id, 0) + (dealt.damage_dealt)
    return damage
