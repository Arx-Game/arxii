"""Companion orders for an opponent's round."""

from __future__ import annotations

from world.combat.constants import CombatAllegiance
from world.combat.models import CombatOpponent


def _get_companion_order(opponent: CombatOpponent, round_number: int) -> object | None:
    """Fetch the CompanionOrder for an ALLY summon this round, if any (#1921).

    Returns None for non-summons or when no order exists.
    """
    if opponent.summoned_by_id is None or opponent.allegiance != CombatAllegiance.ALLY:
        return None

    from world.companions.models import Companion, CompanionOrder  # noqa: PLC0415

    try:
        companion = Companion.objects.get(
            owner_id=opponent.summoned_by_id,
            released_at__isnull=True,
        )
    except (Companion.DoesNotExist, Companion.MultipleObjectsReturned):
        return None

    return CompanionOrder.objects.filter(
        companion=companion,
        encounter=opponent.encounter,
        round_number=round_number,
    ).first()


# Sentinel for the HOLD companion order — distinct from ``None`` (no order) and
# from a directed target list (ATTACK_TARGET) so the caller can branch cleanly.
_COMPANION_HOLD = object()


def _apply_companion_order(
    opponent: CombatOpponent,
    round_number: int,
    target_pool: list,
) -> list | object | None:
    """Apply a companion order to narrow or skip the opponent's target pool.

    A HOLD order returns ``_COMPANION_HOLD`` (skip this round). An ATTACK_TARGET
    order narrows *target_pool* to the directed opponent if still alive, and
    returns that list. Returns ``None`` when no companion order is active, when
    the order doesn't match, or when the directed target is dead/gone (fall back
    to auto-selection).

    Args:
        opponent: The ``CombatOpponent`` to check for a companion order.
        round_number: The current round number.
        target_pool: The current target pool (used for ATTACK_TARGET narrowing).

    Returns:
        ``_COMPANION_HOLD`` when the order is HOLD (skip), a narrowed target list
        when the order is ATTACK_TARGET and the target is alive, or ``None`` when
        no companion order applies or the directed target is gone.
    """
    companion_order = _get_companion_order(opponent, round_number)
    if companion_order is None:
        return None

    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415

    if companion_order.order_kind == CompanionOrderKind.HOLD:
        return _COMPANION_HOLD

    if (
        companion_order.order_kind == CompanionOrderKind.ATTACK_TARGET
        and companion_order.target_opponent_id is not None
    ):
        directed = [opp for opp in target_pool if opp.pk == companion_order.target_opponent_id]
        if directed:
            return directed
    return None
