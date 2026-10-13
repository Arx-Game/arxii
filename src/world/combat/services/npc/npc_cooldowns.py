"""Cooldowns that bar NPC actions."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Q

from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    PendingOpponentAttack,
    ThreatPoolEntry,
)


def _batch_fetch_cooldown_data(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    all_entries: list[ThreatPoolEntry],
    round_number: int,
) -> dict[int, set[int]]:
    """Batch-fetch recently-used entry IDs per opponent for cooldown checks.

    Returns a mapping of opponent_id -> set of entry IDs that are on cooldown.

    #2637: a wind-up entry is committed at DECLARATION, not maturation — it
    does not get a CombatOpponentAction row until it matures rounds later, so
    a pending PendingOpponentAttack's declared_round also counts as "used"
    for cooldown purposes. Batched identically to the CombatOpponentAction
    read below (one extra fixed query, never a query per opponent).
    """
    cooldown_filters, pending_cooldown_filters = _build_cooldown_q_filters(
        opponents, entries_by_pool, round_number
    )

    result: dict[int, set[int]] = defaultdict(set)
    if not cooldown_filters:
        return result

    entry_cooldown_map = {
        e.pk: e.cooldown_rounds for e in all_entries if e.cooldown_rounds is not None
    }

    _collect_cooldown_actions(cooldown_filters, entry_cooldown_map, round_number, result)
    _collect_cooldown_pending(pending_cooldown_filters, entry_cooldown_map, round_number, result)

    return result


def _build_cooldown_q_filters(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    round_number: int,
) -> tuple[Q, Q]:
    """Build OR-ed Q filters for committed and pending cooldown entries.

    Iterates opponents, collecting per-pool cooldown entry IDs and computing
    the earliest allowed round for each, then OR-combines into two Q objects.

    Args:
        opponents: The opponents to build filters for.
        entries_by_pool: Mapping of threat_pool_id to entries.
        round_number: The current round number.

    Returns:
        A tuple of ``(cooldown_filters, pending_cooldown_filters)`` — both empty
        ``Q()`` when no opponent has cooldown entries.
    """
    cooldown_filters = Q()
    pending_cooldown_filters = Q()
    for opponent in opponents:
        opp_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_entry_ids = [e.pk for e in opp_entries if e.cooldown_rounds is not None]
        if not cooldown_entry_ids:
            continue
        max_cooldown = max(e.cooldown_rounds for e in opp_entries if e.cooldown_rounds is not None)
        earliest_allowed = max(1, round_number - max_cooldown + 1)
        cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            round_number__gte=earliest_allowed,
        )
        pending_cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            declared_round__gte=earliest_allowed,
        )
    return cooldown_filters, pending_cooldown_filters


def _collect_cooldown_actions(
    cooldown_filters: Q,
    entry_cooldown_map: dict[int, int],
    round_number: int,
    result: dict[int, set[int]],
) -> dict[int, set[int]]:
    """Collect committed-action cooldown hits into *result*.

    Args:
        cooldown_filters: OR-ed Q filter for ``CombatOpponentAction``.
        entry_cooldown_map: Mapping of entry_id to cooldown_rounds.
        round_number: The current round number.
        result: Accumulating result dict (mutated in place).

    Returns:
        The mutated *result* dict.
    """
    recent_actions = CombatOpponentAction.objects.filter(cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "round_number"
    )
    for opp_id, entry_id, round_num in recent_actions:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)
    return result


def _collect_cooldown_pending(
    pending_cooldown_filters: Q,
    entry_cooldown_map: dict[int, int],
    round_number: int,
    result: dict[int, set[int]],
) -> dict[int, set[int]]:
    """Collect pending-windup cooldown hits into *result*.

    Args:
        pending_cooldown_filters: OR-ed Q filter for ``PendingOpponentAttack``.
        entry_cooldown_map: Mapping of entry_id to cooldown_rounds.
        round_number: The current round number.
        result: Accumulating result dict (mutated in place).

    Returns:
        The mutated *result* dict.
    """
    recent_pending = PendingOpponentAttack.objects.filter(pending_cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "declared_round"
    )
    for opp_id, entry_id, round_num in recent_pending:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)
    return result
