"""Resolving a round's ordered actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    CombatManeuver,
    OpponentStatus,
    WaitingStrikeReason,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.declarations.charge import _resolve_charge_movement
from world.combat.services.npc.npc_action import _resolve_npc_action
from world.combat.services.npc.npc_movement import (
    _cached_opponent_targets,
    _cached_targets,
    broadcast_cannot_reach,
    refit_targets,
)
from world.combat.services.npc.npc_tactics import (
    apply_unanswered_hit_morale,
    narrate_strain,
    run_move_plan,
)
from world.combat.services.rounds.maneuvers import _STANDALONE_MANEUVER_RESOLVERS
from world.combat.services.rounds.waiting_strikes import fire_waiting_strikes
from world.combat.services.techniques.pc_action import _resolve_pc_action
from world.combat.types import ActionOutcome

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.areas.positioning.models import Position
    from world.checks.models import CheckType
    from world.checks.types import CheckResult

    PerformCheckFn = Callable[..., CheckResult]


def _pc_attack_defenders(action: CombatRoundAction) -> list[CombatOpponent]:
    """The opponents a PC's declared attack is aimed at (the waiting-strike defenders).

    A Strike (#4858) is an attack with no technique: its one opponent is the defender.
    """
    if action.maneuver == CombatManeuver.STRIKE:
        target = action.focused_opponent_target
        return [target] if target is not None else []
    if action.maneuver in _STANDALONE_MANEUVER_RESOLVERS or action.focused_action is None:
        return []
    defenders = [t.opponent for t in action.extra_targets.select_related("opponent")]
    target = action.focused_opponent_target
    if target is not None and all(d.pk != target.pk for d in defenders):
        defenders.append(target)
    return defenders


def _resolve_pc_slot(
    entity: CombatParticipant,
    action: CombatRoundAction,
    offense_check_fn: PerformCheckFn | None,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> list[ActionOutcome]:
    """A PC's slot: waiting strikes its attack draws (#4608), then the action itself."""
    defenders = _pc_attack_defenders(action)
    outcomes: list[ActionOutcome] = []
    if defenders:
        if action.maneuver == CombatManeuver.CHARGE:
            # The charge closes in first; the defender's strike answers the arrival.
            _resolve_charge_movement(entity, action)
        strike = fire_waiting_strikes(
            entity.encounter,
            entity,
            reason=WaitingStrikeReason.ATTACKING,
            defenders=defenders,
            offense_check_fn=offense_check_fn,
            defense_check_type=defense_check_type,
            defense_check_fn=defense_check_fn,
        )
        outcomes.extend(strike.outcomes)
        if strike.mover_stopped:
            return outcomes
    outcome = _resolve_pc_action(entity, action, offense_check_fn)
    apply_unanswered_hit_morale(entity, outcome)
    outcomes.append(outcome)
    return outcomes


def _resolve_npc_slot(  # noqa: PLR0913 - the slot carries the loop's check seams
    entity: CombatOpponent,
    move: CombatOpponentMove | None,
    attack_rows: list[CombatOpponentAction],
    offense_check_fn: PerformCheckFn | None,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> list[ActionOutcome]:
    """An NPC's slot: its move plan (arrivals draw waiting strikes), then each attack row.

    The plan (``run_move_plan``, #4609) advances, takes cover, bashes a wall, backs away
    or holds a waiting strike. Each attack row first draws the waiting strikes of its
    defenders (#4608). A strike that stops the opponent cancels the rest of its move and
    every attack still to come. A hit on an opponent that cannot answer the attacker
    shakes its morale. An opponent whose plan and attacks did nothing at all strains
    against the wall that holds it ("{name} strains against {barrier}.").
    """
    encounter = entity.encounter
    outcomes: list[ActionOutcome] = []

    def on_hop(_here: Position, announce: Callable[[], None]) -> bool:
        strike = fire_waiting_strikes(
            encounter,
            entity,
            reason=WaitingStrikeReason.ARRIVED,
            offense_check_fn=offense_check_fn,
            defense_check_type=defense_check_type,
            defense_check_fn=defense_check_fn,
            before_fire=announce,
        )
        outcomes.extend(strike.outcomes)
        return strike.mover_stopped

    moved = run_move_plan(entity, move, attack_rows, on_hop=on_hop)
    if moved.stopped:
        return outcomes
    attacked = _resolve_npc_attacks(
        entity,
        [*attack_rows, *moved.attack_rows],
        outcomes,
        offense_check_fn,
        defense_check_type,
        defense_check_fn,
    )
    if (
        move is not None
        and not moved.progressed
        and not attacked
        and entity.status == OpponentStatus.ACTIVE
    ):
        narrate_strain(entity)
    return outcomes


def _resolve_npc_attacks(  # noqa: PLR0913 - the slot carries the loop's check seams
    entity: CombatOpponent,
    attack_rows: list[CombatOpponentAction],
    outcomes: list[ActionOutcome],
    offense_check_fn: PerformCheckFn | None,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> bool:
    """Resolve the opponent's attack rows into ``outcomes``; True when one was resolved."""
    encounter = entity.encounter
    attacked = False
    for npc_action in attack_rows:
        # Re-fit first, so the defenders are the targets this strike will land on. The
        # resolver's own re-fit then finds nothing to change.
        if not refit_targets(npc_action):
            broadcast_cannot_reach(entity)
            outcomes.append(ActionOutcome(entity_type=ENTITY_TYPE_NPC, entity_label=str(entity)))
            continue
        defenders = [*_cached_targets(npc_action), *_cached_opponent_targets(npc_action)]
        if defenders:
            strike = fire_waiting_strikes(
                encounter,
                entity,
                reason=WaitingStrikeReason.ATTACKING,
                defenders=defenders,
                offense_check_fn=offense_check_fn,
                defense_check_type=defense_check_type,
                defense_check_fn=defense_check_fn,
            )
            outcomes.extend(strike.outcomes)
            if strike.mover_stopped:
                break
        outcome = _resolve_npc_action(entity, npc_action, defense_check_type, defense_check_fn)
        apply_unanswered_hit_morale(entity, outcome)
        outcomes.append(outcome)
        attacked = True
    return attacked


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

    Waiting strikes (#4608) fire inside the slots: on an NPC's arrival in reach after a
    hop, and before any attack resolves against a waiter (``fire_waiting_strikes``).
    """
    npc_moves = npc_moves or {}
    outcomes: list[ActionOutcome] = []
    for entity_type, entity in resolution_order:
        if entity_type == ENTITY_TYPE_PC and isinstance(entity, CombatParticipant):
            if entity.pk in sustaining_participant_ids:
                continue
            action = pc_actions.get(entity.pk)
            if action is not None:
                outcomes.extend(
                    _resolve_pc_slot(
                        entity, action, offense_check_fn, defense_check_type, defense_check_fn
                    )
                )
        elif entity_type == ENTITY_TYPE_NPC and isinstance(entity, CombatOpponent):
            outcomes.extend(
                _resolve_npc_slot(
                    entity,
                    npc_moves.get(entity.pk),
                    npc_actions.get(entity.pk, []),
                    offense_check_fn,
                    defense_check_type,
                    defense_check_fn,
                )
            )
    return outcomes
