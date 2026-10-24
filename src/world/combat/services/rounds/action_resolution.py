"""Resolving a round's ordered actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ENTITY_TYPE_NPC, ENTITY_TYPE_PC
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.npc.npc_action import _resolve_npc_action
from world.combat.services.npc.npc_movement import advance_opponent
from world.combat.services.techniques.pc_action import _resolve_pc_action
from world.combat.types import ActionOutcome

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.models import CheckType
    from world.checks.types import CheckResult

    PerformCheckFn = Callable[..., CheckResult]


def _resolve_actions(  # noqa: PLR0913 - resolution needs all check params
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    npc_actions: dict[int, list[CombatOpponentAction]],
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    offense_check_fn: PerformCheckFn | None,
    *,
    sustaining_participant_ids: frozenset[int] = frozenset(),
    npc_moves: dict[int, CombatOpponentMove] | None = None,
) -> list[ActionOutcome]:
    """Iterate resolution order and resolve each entity's action.

    ``sustaining_participant_ids`` (#2705) — participants who declared a new
    ``SustainedAction`` THIS round. Their ``CombatRoundAction`` row on the
    board is the declaration of the commitment, not an action to resolve —
    the commitment resolves later, at maturation. Precomputed by the caller
    (one query); this loop only checks membership.

    ``npc_moves`` (#4607): each opponent's move plan for the round, keyed by
    opponent pk. An NPC advances once in its slot, before its first attack row
    (whatever ``actions_per_round`` is), and never moves after an attack row
    has resolved (strike then stay).
    """
    npc_moves = npc_moves or {}
    outcomes: list[ActionOutcome] = []
    for entity_type, entity in resolution_order:
        if entity_type == ENTITY_TYPE_PC and isinstance(entity, CombatParticipant):
            if entity.pk in sustaining_participant_ids:
                continue
            action = pc_actions.get(entity.pk)
            if action is not None:
                outcomes.append(_resolve_pc_action(entity, action, offense_check_fn))
        elif entity_type == ENTITY_TYPE_NPC and isinstance(entity, CombatOpponent):
            attack_rows = npc_actions.get(entity.pk, [])
            advance_opponent(entity, npc_moves.get(entity.pk), attack_rows)
            outcomes.extend(
                _resolve_npc_action(entity, npc_action, defense_check_type, defense_check_fn)
                for npc_action in attack_rows
            )
    return outcomes
