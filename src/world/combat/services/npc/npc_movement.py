"""NPC movement on the battle map: reach-aware planning, advance, and target re-fit (#4607).

Slice 2 of #4576. Selection writes one ``CombatOpponentMove`` plan row per opponent per
round beside its attack rows (``plan_opponent_round`` in ``npc_selection``). In the
opponent's resolution slot ``advance_opponent`` re-plans against live positions and walks
before its first attack row; ``refit_targets`` then drops stored targets a strike no
longer reaches. Unplaced combatants stay lenient everywhere: no position means reach is
true and nothing moves.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.services import (
    enter_aerial,
    find_path,
    force_move_to_position,
    leave_aerial,
    materialize_aerial_layer,
    step_costs,
    strike_reaches,
)
from world.combat.constants import (
    OpponentMoveKind,
    OpponentStatus,
    StrikeDelivery,
    TargetingMode,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
)
from world.combat.services.npc.npc_targeting import (
    _npc_action_target_pool,
    _select_opponent_targets,
    _select_targets,
    _targetable_participants,
)

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.combat.types import MovementProfile

CANNOT_REACH_LINE = "{name} cannot reach anyone."
MOVES_TO_LINE = "{name} moves to {position}."


class ReachMemo:
    """Memoized ``strike_reaches`` for one planning pass.

    ``strike_reaches`` costs a query per MELEE call; a path search asks it for every
    node it visits, for every target, so one pass shares the answers.
    """

    def __init__(self) -> None:
        self._known: dict[tuple[int, int, str], bool] = {}

    def reaches(
        self, attacker_pos: Position | None, target_pos: Position | None, delivery: str
    ) -> bool:
        if attacker_pos is None or target_pos is None:
            return True
        key = (attacker_pos.pk, target_pos.pk, delivery)
        if key not in self._known:
            self._known[key] = strike_reaches(attacker_pos, target_pos, delivery)
        return self._known[key]


def target_position(target: CombatParticipant | CombatOpponent) -> Position | None:
    """A target's live position (the cached property ``_commit_position`` clears on a move).

    An opponent whose game object is gone (cleaned up, or nulled under a cached row) has
    no position.
    """
    if isinstance(target, CombatOpponent) and target.objectdb is None:
        return None
    return target.current_position


def prepare_mover(opponent: CombatOpponent, profile: MovementProfile) -> Position | None:
    """The opponent's live position, with the aerial layer built first for a flier.

    A FLIES mover searches the union of ground and aerial positions; ``find_path`` never
    builds the layer itself.
    """
    origin = target_position(opponent)
    if origin is None:
        return None
    if profile.traversal == CreatureTraversal.FLIES and origin.room is not None:
        materialize_aerial_layer(origin.room)
    return origin


def _cheapest_route(
    origin: Position,
    goal_test: Callable[[Position], bool],
    profile: MovementProfile,
) -> list[Position] | None:
    """The cheapest route to a goal node, or None; the route may exceed the hop budget."""
    return find_path(origin, goal_test, traversal=profile.traversal)


def can_strike_this_round(
    origin: Position | None,
    target_pos: Position | None,
    delivery: str,
    *,
    profile: MovementProfile,
    memo: ReachMemo,
) -> bool:
    """Whether a mover at ``origin`` can get within ``delivery`` reach of ``target_pos``
    with at most ``profile.speed_hops`` hops. Either position missing: True (lenient)."""
    if origin is None or target_pos is None:
        return True
    path = _cheapest_route(origin, lambda node: memo.reaches(node, target_pos, delivery), profile)
    if path is None:
        return False
    return sum(step_costs(path, traversal=profile.traversal)) <= profile.speed_hops


def reachable_pools_by_delivery(
    origin: Position | None,
    target_pool: list,
    deliveries: set[str],
    *,
    profile: MovementProfile,
    memo: ReachMemo,
) -> dict[str, list]:
    """For each delivery, the targets in ``target_pool`` strikeable this round."""
    positions = [(t, target_position(t)) for t in target_pool]
    return {
        delivery: [
            t
            for t, pos in positions
            if can_strike_this_round(origin, pos, delivery, profile=profile, memo=memo)
        ]
        for delivery in deliveries
    }


def nearest_hostile_position(
    origin: Position | None,
    hostiles: list,
    profile: MovementProfile,
) -> Position | None:
    """The position of the hostile cheapest to walk to, or None (unplaced or no route)."""
    if origin is None:
        return None
    hostile_pks = {pos.pk for pos in (target_position(t) for t in hostiles) if pos is not None}
    if not hostile_pks:
        return None
    path = _cheapest_route(origin, lambda node: node.pk in hostile_pks, profile)
    return path[-1] if path else None


def write_move_plan(
    opponent: CombatOpponent,
    round_number: int,
    *,
    goal_position: Position | None = None,
) -> CombatOpponentMove:
    """Write the opponent's one ADVANCE plan for the round (never a second row)."""
    move, _ = CombatOpponentMove.objects.get_or_create(
        opponent=opponent,
        round_number=round_number,
        defaults={"kind": OpponentMoveKind.ADVANCE, "goal_position": goal_position},
    )
    return move


# ---------------------------------------------------------------------------
# Advance (resolution slot, before the first attack row)
# ---------------------------------------------------------------------------


def _cached_targets(npc_action: CombatOpponentAction) -> list[CombatParticipant]:
    try:
        return npc_action.cached_targets
    except AttributeError:
        return list(npc_action.targets.all())


def _cached_opponent_targets(npc_action: CombatOpponentAction) -> list[CombatOpponent]:
    try:
        return npc_action.cached_opponent_targets
    except AttributeError:
        return list(npc_action.opponent_targets.all())


def _live_target_pool(opponent: CombatOpponent) -> tuple[list, bool]:
    """Every live hostile this opponent could strike, allegiance-aware, read now."""
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    encounter = opponent.encounter
    active_opponents = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.ACTIVE)
    )
    return _npc_action_target_pool(
        opponent,
        _targetable_participants(encounter),
        encounter,
        allegiances=effective_allegiances(active_opponents),
        active_opponents=active_opponents,
    )


def _is_live(target: CombatParticipant | CombatOpponent) -> bool:
    if isinstance(target, CombatParticipant):
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415

        return target.status == ParticipantStatus.ACTIVE
    return target.status == OpponentStatus.ACTIVE


def _goal_pairs(
    opponent: CombatOpponent,
    attack_rows: list[CombatOpponentAction],
) -> list[tuple[Position, str]]:
    """(target position, delivery) pairs the advance heads for, placed targets only.

    The live targets of this round's attack rows, each with its row's delivery; when
    none is left, every live hostile with MELEE. A live stored target with no position
    is always in reach (lenient), so then there is nothing to head for.
    """
    pairs: list[tuple[Position, str]] = []
    for row in attack_rows:
        delivery = row.threat_entry.delivery
        for target in [*_cached_targets(row), *_cached_opponent_targets(row)]:
            if not _is_live(target):
                continue
            pos = target_position(target)
            if pos is None:
                return []
            pairs.append((pos, delivery))
    if pairs:
        return pairs
    hostiles, _ = _live_target_pool(opponent)
    return [
        (pos, StrikeDelivery.MELEE)
        for pos in (target_position(t) for t in hostiles)
        if pos is not None
    ]


def _truncate_to_budget(path: list[Position], profile: MovementProfile) -> list[Position]:
    """The prefix of ``path`` the mover can walk with ``profile.speed_hops`` hops."""
    walked = [path[0]]
    spent = 0
    for position, cost in zip(path[1:], step_costs(path, traversal=profile.traversal), strict=True):
        if spent + cost > profile.speed_hops:
            break
        spent += cost
        walked.append(position)
    return walked


def _walk(opponent: CombatOpponent, path: list[Position]) -> Position:
    """Step the opponent's object along ``path``; returns where it ended.

    Ground to its own aerial twin takes flight (``enter_aerial``); aerial to its ground
    anchor lands (``leave_aerial``, which may tear the aerial layer down, so the walk
    stops at the next aerial node after a landing). Every other step is
    ``force_move_to_position``: the path service already checked the edge, and a climber
    must cross a gated wall that ``move_to_position`` refuses.
    """
    objectdb = opponent.objectdb
    here = path[0]
    landed = False
    for there in path[1:]:
        if landed and there.kind == PositionKind.AERIAL:
            break
        if there.kind == PositionKind.AERIAL and there.elevation_anchor_id == here.pk:
            enter_aerial(objectdb)
        elif here.kind == PositionKind.AERIAL and here.elevation_anchor_id == there.pk:
            leave_aerial(objectdb)
            landed = True
        else:
            force_move_to_position(objectdb, there)
        here = there
    return here


def _advance_route(
    opponent: CombatOpponent,
    origin: Position,
    pairs: list[tuple[Position, str]],
    profile: MovementProfile,
) -> list[Position] | None:
    """The full (uncut) route the advance takes, or None to stay put.

    None when there is no goal, the origin already strikes one, or nothing is reachable.
    """
    if not pairs:
        return None
    memo = ReachMemo()

    def strikes_a_goal(node: Position) -> bool:
        return any(memo.reaches(node, pos, delivery) for pos, delivery in pairs)

    if strikes_a_goal(origin):
        return None
    path = _cheapest_route(origin, strikes_a_goal, profile)
    if path is not None:
        return path
    hostiles, _ = _live_target_pool(opponent)
    hostile_pks = {p.pk for p in (target_position(t) for t in hostiles) if p is not None}
    return _cheapest_route(origin, lambda node: node.pk in hostile_pks, profile)


def advance_opponent(
    opponent: CombatOpponent,
    move_row: CombatOpponentMove | None,
    attack_rows: list[CombatOpponentAction] | None = None,
) -> Position | None:
    """Run an opponent's ADVANCE plan in its resolution slot; returns where it moved, or None.

    Re-plans against live positions (PCs moved at declaration). Heads for a node from
    which some goal target (``_goal_pairs``) is struck; already there, it stays. With no
    route to that, it walks toward the nearest live hostile. With no route at all it
    stays (physically blocked). The walk is cut to ``speed_hops``. A swarm is one row, so
    it moves as one body. Narrates ``"{name} moves to {position}."`` when it moved.
    """
    if move_row is None or move_row.kind != OpponentMoveKind.ADVANCE:
        return None
    if opponent.status != OpponentStatus.ACTIVE or opponent.objectdb is None:
        return None
    profile = opponent.movement_profile
    origin = prepare_mover(opponent, profile)
    if origin is None:
        return None
    if attack_rows is None:
        attack_rows = list(
            CombatOpponentAction.objects.filter(
                opponent=opponent, round_number=move_row.round_number
            ).select_related("threat_entry")
        )
    path = _advance_route(opponent, origin, _goal_pairs(opponent, attack_rows), profile)
    if path is None:
        return None
    walked = _truncate_to_budget(path, profile)
    if len(walked) <= 1:
        return None
    final = _walk(opponent, walked)

    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(
        encounter=opponent.encounter,
        narration=MOVES_TO_LINE.format(name=opponent.name, position=final.name),
        target_personas=[],
    )
    return final


# ---------------------------------------------------------------------------
# Re-fit (before each attack row)
# ---------------------------------------------------------------------------


def _repick_single_target(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    origin: Position,
    *,
    targeting_participants: bool,
) -> list:
    """Re-pick a lost single target among the live hostiles now in reach."""
    entry = npc_action.threat_entry
    pool, pool_is_participants = _live_target_pool(opponent)
    if pool_is_participants != targeting_participants:
        return []
    memo = ReachMemo()
    in_reach = [t for t in pool if memo.reaches(origin, target_position(t), entry.delivery)]
    if targeting_participants:
        return _select_targets(entry, in_reach)
    return _select_opponent_targets(entry, in_reach)


def refit_targets(npc_action: CombatOpponentAction) -> bool:
    """Drop the stored targets this action's strike no longer reaches; False when none is left.

    Reads live positions. A single-target action that lost its target re-picks among the
    reachable live hostiles with the entry's own selection mode; an area action keeps
    the targets still in reach. Writes the relation (``.set``) and the prefetched
    ``cached_targets`` / ``cached_opponent_targets`` the resolver reads. An unplaced
    attacker, or an action with no stored target, is left alone (True).
    """
    opponent = npc_action.opponent
    origin = target_position(opponent)
    targets = _cached_targets(npc_action)
    opponent_targets = _cached_opponent_targets(npc_action)
    if origin is None or not (targets or opponent_targets):
        return True
    delivery = npc_action.threat_entry.delivery
    memo = ReachMemo()
    kept = [t for t in targets if memo.reaches(origin, target_position(t), delivery)]
    kept_opponents = [
        t for t in opponent_targets if memo.reaches(origin, target_position(t), delivery)
    ]
    if len(kept) == len(targets) and len(kept_opponents) == len(opponent_targets):
        return True
    if (
        not kept
        and not kept_opponents
        and npc_action.threat_entry.targeting_mode == TargetingMode.SINGLE
    ):
        repicked = _repick_single_target(
            opponent, npc_action, origin, targeting_participants=bool(targets)
        )
        if targets:
            kept = repicked
        else:
            kept_opponents = repicked
    npc_action.targets.set(kept)
    npc_action.opponent_targets.set(kept_opponents)
    npc_action.cached_targets = kept
    npc_action.cached_opponent_targets = kept_opponents
    return bool(kept or kept_opponents)


def broadcast_cannot_reach(opponent: CombatOpponent) -> None:
    """Say that an attack row was skipped because no target is in reach."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(
        encounter=opponent.encounter,
        narration=CANNOT_REACH_LINE.format(name=opponent.name),
        target_personas=[],
    )
