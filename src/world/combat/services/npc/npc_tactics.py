"""NPC tactics: what an opponent does with its round, by how cleverly it fights (#4609).

Slice 4 of #4576. All NPC planning decisions sit here. Selection (``plan_opponent_round``)
asks the ladder for the opponent's one move plan and any attack rows; the resolve loop
asks ``run_move_plan`` to carry the plan out in the opponent's slot, re-planned against
live positions. The ladder runs in order and the first step that applies wins:

1. Broken morale: back away by real movement (RETREAT), and leave the fight once no
   enemy can reach it or after ``retreat_rounds_limit`` rounds. Cornered, it fights.
2. Hit this round by an attacker it cannot answer: make for the nearest roofed or
   screened position the attacker cannot strike (SHELTER). Every tactics level does
   this: cover is instinct. A tactical opponent prefers one that keeps an ally beside
   it. It still strikes anyone in reach when it gets there.
3. A hostile in reach after moving: attack, with the existing selection rules. A
   cunning or tactical opponent first spends a grounding entry on a flier that hits it
   and that nothing else it has can reach.
4. No hostile in reach: walk toward the nearest position a strike lands from (ADVANCE).
5. A breakable wall blocks the shortest way: bash it (BASH). A mindless opponent always
   does; the others only when the group can bring it down within ``bash_rounds_limit``
   rounds, and otherwise go around, or toward another enemy they can reach.
6. Nothing gets it nearer this round: bash the wall in the way anyway (all levels),
   else wait once for an opening (WAIT, cunning and tactical, never twice running),
   else stand. An opponent with no move left at all says it strains against the wall.

Everything the ladder reads is derived: who is hitting an opponent comes from this
round's declarations and attack rows, the waiting cap from last round's move row, the
retreat count from the rows before it. Nothing new is stored.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.models import Position, PositionEdge
from world.areas.positioning.services import (
    barrier_integrity,
    damage_barrier,
    edge_between,
    find_path,
    first_closed_edge,
    is_breakable_barrier,
    path_costs_from,
    step_costs,
    strike_reaches,
)
from world.checks.constants import EffectType
from world.combat.constants import (
    BARRIER_GIVES_WAY_NARRATION,
    BATTERS_BARRIER_NARRATION,
    NPC_FLEES_NARRATION,
    NPC_WAITS_NARRATION,
    STRAINS_AGAINST_NARRATION,
    CreatureTactics,
    OpponentMoveKind,
    OpponentStatus,
    StrikeDelivery,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    NpcTacticsConfig,
    ThreatPoolEntry,
)
from world.combat.services.npc.npc_movement import (
    ReachMemo,
    _is_live,
    _live_target_pool,
    _truncate_to_budget,
    advance_opponent,
    can_strike_this_round,
    entry_grounds_fliers,
    mover_origin,
    target_position,
    walk_and_announce,
    write_move_plan,
)
from world.combat.services.npc.npc_targeting import (
    _select_opponent_targets,
    _select_targets,
    _set_npc_action_targets,
)
from world.combat.types import (
    ActionOutcome,
    OpponentDamageResult,
    SlotMoveResult,
    TacticsInputs,
)
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.combat.services.npc.npc_movement import HopHook
    from world.combat.services.npc.npc_selection import NpcRoundContext
    from world.combat.types import MovementProfile

Combatant = CombatParticipant | CombatOpponent

# A position no enemy can walk to is as far from them as a position gets.
_UNREACHABLE = 10**6
_GENERIC_WALL = "the wall"


# ---------------------------------------------------------------------------
# Round inputs (batched once per round, beside NpcRoundContext)
# ---------------------------------------------------------------------------


def build_tactics_inputs(
    encounter: CombatEncounter,
    opponents: list[CombatOpponent],
    all_active: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
) -> TacticsInputs:
    """Batch-fetch what the ladder reads this round (a fixed number of queries)."""
    from world.checks.models import ConsequenceEffect  # noqa: PLC0415

    config = NpcTacticsConfig.load()
    round_number = encounter.round_number
    lookback = max(config.retreat_rounds_limit, 1)
    prior: dict[int, dict[int, str]] = defaultdict(dict)
    for opponent_id, past_round, kind in CombatOpponentMove.objects.filter(
        opponent__in=opponents,
        round_number__gte=round_number - lookback,
        round_number__lt=round_number,
    ).values_list("opponent_id", "round_number", "kind"):
        prior[opponent_id][past_round] = kind

    missing = {o.threat_pool_id for o in all_active if o.threat_pool_id} - set(entries_by_pool)
    ally_entries: dict[int, list[ThreatPoolEntry]] = defaultdict(list, entries_by_pool)
    for entry in ThreatPoolEntry.objects.filter(pool_id__in=missing):
        ally_entries[entry.pool_id].append(entry)

    grounding_consequences = set(
        ConsequenceEffect.objects.filter(effect_type=EffectType.REMOVE_FLIGHT).values_list(
            "consequence_id", flat=True
        )
    )
    grounding: set[int] = set()
    if grounding_consequences:
        for entries in ally_entries.values():
            for entry in entries:
                pool = entry.on_hit_consequence_pool
                if pool is not None and any(
                    wc.consequence.pk in grounding_consequences for wc in pool.cached_consequences
                ):
                    grounding.add(entry.pk)

    return TacticsInputs(
        config=config,
        prior_move_kinds=prior,
        aimed_at=_aimed_at(encounter, all_active),
        grounding_entry_ids=grounding,
        ally_entries_by_pool=ally_entries,
    )


def _aimed_at(
    encounter: CombatEncounter, all_active: list[CombatOpponent]
) -> dict[int, list[Combatant]]:
    """Opponent pk -> the fighters whose action this round is aimed at it.

    A player's declared technique at it (its focused target or an extra target, or a
    waiting strike that already went off at it), and an opponent's attack row at it.
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415

    round_number = encounter.round_number
    by_pk = {o.pk: o for o in all_active}
    aimed: dict[int, dict[tuple[str, int], Combatant]] = defaultdict(dict)
    declared = list(
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            participant__status=ParticipantStatus.ACTIVE,
            round_number=round_number,
            focused_action__isnull=False,
        ).select_related("participant__character_sheet__character")
    )
    for action in declared:
        if action.focused_opponent_target_id is not None:
            aimed[action.focused_opponent_target_id][("pc", action.participant_id)] = (
                action.participant
            )
    by_action = {a.pk: a for a in declared}
    for action_id, opponent_id in CombatRoundActionTarget.objects.filter(
        action_id__in=list(by_action)
    ).values_list("action_id", "opponent_id"):
        action = by_action[action_id]
        aimed[opponent_id][("pc", action.participant_id)] = action.participant
    for attacker_id, target_id in CombatOpponentAction.opponent_targets.through.objects.filter(
        combatopponentaction__round_number=round_number,
        combatopponentaction__opponent__encounter=encounter,
    ).values_list("combatopponentaction__opponent_id", "combatopponent_id"):
        attacker = by_pk.get(attacker_id)
        if attacker is not None:
            aimed[target_id][("npc", attacker_id)] = attacker
    return {pk: list(found.values()) for pk, found in aimed.items()}


# ---------------------------------------------------------------------------
# Small derived facts
# ---------------------------------------------------------------------------


def is_mindless(profile: MovementProfile) -> bool:
    return profile.tactics == CreatureTactics.MINDLESS


def usable_entries(
    entries: list[ThreatPoolEntry], profile: MovementProfile, grounding: set[int]
) -> list[ThreatPoolEntry]:
    """The entries the opponent will use: a mindless one never picks a grounding entry."""
    if not is_mindless(profile):
        return list(entries)
    return [e for e in entries if e.pk not in grounding]


def bash_chip(entry: ThreatPoolEntry, opponent: CombatOpponent) -> int:
    """What one blow of ``entry`` takes off a wall: base damage times the opponent's
    damage multiplier, no defence roll. At least 1 for an entry that deals damage."""
    if entry.base_damage <= 0:
        return 0
    return max(1, int(entry.base_damage * opponent.damage_multiplier))


def best_bash_entry(
    entries: list[ThreatPoolEntry], opponent: CombatOpponent
) -> ThreatPoolEntry | None:
    """The opponent's hardest-hitting melee entry that strikes at once, or None."""
    melee = [
        e
        for e in entries
        if e.delivery == StrikeDelivery.MELEE and e.windup_rounds == 0 and bash_chip(e, opponent)
    ]
    return max(melee, key=lambda e: (bash_chip(e, opponent), -e.pk), default=None)


def wait_entry(entries: list[ThreatPoolEntry]) -> ThreatPoolEntry | None:
    """A melee entry to hold for a waiting strike (melee reaches the same or an
    adjacent position), or None. Prefers the heaviest."""
    melee = [e for e in entries if e.delivery == StrikeDelivery.MELEE and e.windup_rounds == 0]
    return max(melee, key=lambda e: (e.base_damage, -e.pk), default=None)


def barrier_label(edge: PositionEdge) -> str:
    """How the round log names a wall: its gate's name, its Rampart, or "the wall"."""
    if edge.gating_challenge_id is not None:
        return edge.gating_challenge.template.name
    if edge.source_rampart_id is not None:
        return f"the {edge.source_rampart.element_profile.name} Rampart"
    return _GENERIC_WALL


def _say(encounter: CombatEncounter, line: str) -> None:
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(
        encounter=encounter, narration=line, target_personas=[], deliver_telnet=True
    )


def _traversal_of(combatant: Combatant) -> str:
    """How a fighter gets about, for measuring path distance from it."""
    if isinstance(combatant, CombatOpponent):
        return combatant.movement_profile.traversal
    position = target_position(combatant)
    if position is not None and position.kind == PositionKind.AERIAL:
        return CreatureTraversal.FLIES
    return CreatureTraversal.WALKS


def _placed(combatants: list) -> list[tuple[Combatant, Position]]:
    return [(c, pos) for c in combatants if (pos := target_position(c)) is not None]


# ---------------------------------------------------------------------------
# Unanswerable attackers (step 2 and the morale hit)
# ---------------------------------------------------------------------------


def can_answer(
    origin: Position | None,
    attacker_pos: Position | None,
    entries: list[ThreatPoolEntry],
    *,
    profile: MovementProfile,
    memo: ReachMemo,
) -> bool:
    """Whether any of ``entries`` can strike ``attacker_pos`` this round (moving first).

    Either position missing: True (an unplaced fighter is always in reach). Cooldowns
    are not consulted: an entry the opponent has is an answer it can give.
    """
    if origin is None or attacker_pos is None:
        return True
    return any(
        can_strike_this_round(origin, attacker_pos, e.delivery, profile=profile, memo=memo)
        for e in entries
    )


def unanswerable_attackers(  # noqa: PLR0913 - the ladder's per-opponent inputs
    opponent: CombatOpponent,
    origin: Position | None,
    entries: list[ThreatPoolEntry],
    *,
    profile: MovementProfile,
    inputs: TacticsInputs,
    memo: ReachMemo,
) -> list[tuple[Combatant, Position]]:
    """The live fighters hitting ``opponent`` this round that it cannot hit back."""
    if origin is None:
        return []
    attackers = [a for a in inputs.aimed_at.get(opponent.pk, []) if _is_live(a)]
    return [
        (a, pos)
        for a, pos in _placed(attackers)
        if not can_answer(origin, pos, entries, profile=profile, memo=memo)
    ]


def apply_unanswered_hit_morale(attacker: Combatant, outcome: ActionOutcome) -> None:
    """Each hit ``attacker`` landed on an opponent that cannot answer it shakes that
    opponent by ``unanswered_hit_morale`` (a tier without morale takes its share)."""
    from world.combat.morale import apply_morale_damage  # noqa: PLC0415

    victims = [
        r.opponent_id
        for r in outcome.damage_results
        if isinstance(r, OpponentDamageResult) and r.opponent_id and r.damage_dealt > 0
    ]
    attacker_pos = target_position(attacker)
    if not victims or attacker_pos is None:
        return
    struck = [
        o
        for o in CombatOpponent.objects.filter(pk__in=victims, status=OpponentStatus.ACTIVE)
        if not (isinstance(attacker, CombatOpponent) and attacker.pk == o.pk)
    ]
    entries_by_pool: dict[int, list[ThreatPoolEntry]] = defaultdict(list)
    for entry in ThreatPoolEntry.objects.filter(
        pool_id__in={o.threat_pool_id for o in struck if o.threat_pool_id}
    ).select_related("on_hit_consequence_pool"):
        entries_by_pool[entry.pool_id].append(entry)
    unanswered = [
        o
        for o in struck
        if not _answers_from_its_place(o, attacker_pos, entries_by_pool[o.threat_pool_id])
    ]
    for opponent in unanswered:
        amount = _unanswered_morale(opponent, victims.count(opponent.pk))
        if amount > 0:
            apply_morale_damage(opponent, amount)


def _answers_from_its_place(
    opponent: CombatOpponent, attacker_pos: Position, entries: list[ThreatPoolEntry]
) -> bool:
    """Whether ``opponent`` can hit ``attacker_pos`` with an entry it would use."""
    profile = opponent.movement_profile
    if is_mindless(profile):
        entries = [e for e in entries if not entry_grounds_fliers(e)]
    with mover_origin(opponent, profile) as origin:
        return can_answer(origin, attacker_pos, entries, profile=profile, memo=ReachMemo())


def _unanswered_morale(opponent: CombatOpponent, hits: int) -> int:
    """The morale ``hits`` unanswered hits take: the tuning row's amount per hit, the
    spectacle settings' share of it for a tier without morale."""
    from world.combat.models import SpectacleConfig  # noqa: PLC0415
    from world.combat.morale import mindless_share, tier_has_morale  # noqa: PLC0415

    amount = NpcTacticsConfig.load().unanswered_hit_morale * hits
    if tier_has_morale(opponent):
        return amount
    return mindless_share(amount, mindless_percent=SpectacleConfig.load().mindless_percent)


# ---------------------------------------------------------------------------
# Shelter (step 2)
# ---------------------------------------------------------------------------


def _safe_from(attacker_positions: list[Position]) -> Callable[[Position], bool]:
    def safe(node: Position) -> bool:
        return not any(
            strike_reaches(pos, node, StrikeDelivery.MISSILE) for pos in attacker_positions
        )

    return safe


def shelter_goal(  # noqa: PLR0913 - the ladder's per-opponent inputs
    opponent: CombatOpponent,
    origin: Position | None,
    attackers: list[tuple[Combatant, Position]],
    *,
    profile: MovementProfile,
    allies: list[CombatOpponent],
    memo: ReachMemo,
) -> Position | None:
    """The roofed or screened position to run for, or None when shelter does not apply.

    None when nothing unanswerable hits it, when where it stands is already out of every
    such attacker's reach, or when no covered position out of their reach can be walked
    to. A tactical opponent takes one it can reach this round with an ally beside it,
    if there is one; otherwise the nearest.
    """
    if origin is None or not attackers:
        return None
    safe = _safe_from([pos for _a, pos in attackers])
    if safe(origin):
        return None

    def covered(node: Position) -> bool:
        return (node.is_roofed or node.screens_ranged) and safe(node)

    if profile.tactics == CreatureTactics.TACTICAL:
        ally_positions = [pos for _a, pos in _placed([a for a in allies if a.pk != opponent.pk])]

        def covered_with_ally(node: Position) -> bool:
            return covered(node) and any(
                memo.reaches(node, pos, StrikeDelivery.MELEE) for pos in ally_positions
            )

        path = find_path(origin, covered_with_ally, traversal=profile.traversal)
        if path is not None and _route_cost(path, profile) <= profile.speed_hops:
            return path[-1]
    path = find_path(origin, covered, traversal=profile.traversal)
    return path[-1] if path is not None else None


def _route_cost(path: list[Position], profile: MovementProfile, *, through: bool = False) -> int:
    return sum(step_costs(path, traversal=profile.traversal, through_barriers=through))


# ---------------------------------------------------------------------------
# Grounding (step 7)
# ---------------------------------------------------------------------------


def grounding_strike(  # noqa: PLR0913 - the ladder's per-opponent inputs
    origin: Position | None,
    attackers: list[Combatant],
    eligible: list[ThreatPoolEntry],
    usable: list[ThreatPoolEntry],
    *,
    profile: MovementProfile,
    inputs: TacticsInputs,
    memo: ReachMemo,
) -> tuple[ThreatPoolEntry, Combatant] | None:
    """A grounding entry and the flier to spend it on, or None.

    A flier hitting the opponent this round that no entry of the opponent's other than
    a grounding one can reach, and an eligible grounding entry that can. Never for a
    mindless opponent (its ``usable`` list already lacks grounding entries).
    """
    if is_mindless(profile) or origin is None:
        return None
    grounders = [e for e in eligible if e.pk in inputs.grounding_entry_ids and e.windup_rounds == 0]
    if not grounders:
        return None
    others = [e for e in usable if e.pk not in inputs.grounding_entry_ids]
    for attacker, pos in _placed(attackers):
        if pos.kind != PositionKind.AERIAL:
            continue
        if can_answer(origin, pos, others, profile=profile, memo=memo):
            continue
        for entry in grounders:
            if can_strike_this_round(origin, pos, entry.delivery, profile=profile, memo=memo):
                return entry, attacker
    return None


def write_grounding_attack(
    opponent: CombatOpponent,
    encounter: CombatEncounter,
    entry: ThreatPoolEntry,
    target: Combatant,
) -> CombatOpponentAction:
    """The attack row a grounding strike makes, aimed at the one flier."""
    action = CombatOpponentAction.objects.create(
        opponent=opponent, round_number=encounter.round_number, threat_entry=entry
    )
    _set_npc_action_targets(
        action,
        entry,
        [target],
        targeting_participants=isinstance(target, CombatParticipant),
        rotation=0,
    )
    return action


# ---------------------------------------------------------------------------
# Approach, bash and wait (steps 4 to 8)
# ---------------------------------------------------------------------------


def group_chip(
    edge: PositionEdge,
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
) -> int:
    """The summed best melee chip of every active opponent on ``opponent``'s side within
    one hop of either end of the wall. Computed once per wall per round."""
    inputs = ctx.tactics
    key = edge.pk
    if key in inputs.wall_chips:
        return inputs.wall_chips[key]
    side = ctx.allegiances.get(opponent.pk, Allegiance.ENEMY)
    ends = [edge.position_a, edge.position_b]
    memo = ctx.reach_memo
    total = 0
    for ally in ctx.all_active:
        if ctx.allegiances.get(ally.pk, Allegiance.ENEMY) != side:
            continue
        pos = target_position(ally)
        if pos is None or not any(
            pos.pk == end.pk or memo.reaches(pos, end, StrikeDelivery.MELEE) for end in ends
        ):
            continue
        entry = best_bash_entry(inputs.ally_entries_by_pool.get(ally.threat_pool_id, []), ally)
        if entry is not None:
            total += bash_chip(entry, ally)
    inputs.wall_chips[key] = total
    return total


def can_break_in_time(edge: PositionEdge, opponent: CombatOpponent, ctx: NpcRoundContext) -> bool:
    """The bash-able test: live integrity <= ``bash_rounds_limit`` x the group's chip."""
    integrity = barrier_integrity(edge)
    if integrity is None:
        return False
    return integrity <= ctx.tactics.config.bash_rounds_limit * group_chip(edge, opponent, ctx)


def _approach_test(
    hostile_positions: list[Position], deliveries: set[str], memo: ReachMemo
) -> Callable[[Position], bool]:
    def strikes(node: Position) -> bool:
        return any(memo.reaches(node, pos, d) for pos in hostile_positions for d in deliveries)

    return strikes


def plan_approach(  # noqa: PLR0913 - the ladder's steps 4 to 8 read as one table
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
    origin: Position | None,
    target_pool: list,
    eligible: list[ThreatPoolEntry],
    usable: list[ThreatPoolEntry],
    *,
    profile: MovementProfile,
) -> None:
    """Write the move plan of an opponent with no hostile in reach this round."""
    round_number = ctx.encounter.round_number
    hostiles = [pos for _t, pos in _placed(target_pool)]
    if origin is None or not hostiles:
        write_plan(opponent, ctx)
        return
    deliveries = {e.delivery for e in usable} or {StrikeDelivery.MELEE}
    approach = _approach_test(hostiles, deliveries, ctx.reach_memo)
    free = find_path(origin, approach, traversal=profile.traversal)
    wall = find_path(origin, approach, traversal=profile.traversal, through_barriers=True)
    blocking = None
    if wall is not None:
        blocking = first_closed_edge(wall, traversal=profile.traversal)
        if (
            blocking is not None
            and free is not None
            and _route_cost(free, profile) <= _route_cost(wall, profile, through=True)
        ):
            blocking = None  # going around costs no more than going through
    advance_to = free[-1] if free is not None else None
    can_advance = free is not None and len(_truncate_to_budget(free, profile)) > 1
    basher = best_bash_entry(eligible, opponent)

    if (
        blocking is not None
        and basher is not None
        and (is_mindless(profile) or can_break_in_time(blocking, opponent, ctx) or not can_advance)
    ):
        write_plan(
            opponent, ctx, kind=OpponentMoveKind.BASH, barrier_edge=blocking, threat_entry=basher
        )
        return
    if can_advance:
        write_plan(opponent, ctx, goal_position=advance_to)
        return
    # Nothing gets it nearer this round (zero-hop).
    stuck_at = _unaffordable_wall(free) if blocking is None else blocking
    if stuck_at is not None and basher is not None:
        write_plan(
            opponent, ctx, kind=OpponentMoveKind.BASH, barrier_edge=stuck_at, threat_entry=basher
        )
        return
    held = wait_entry(eligible)
    waited_last_round = (
        ctx.tactics.prior_move_kinds.get(opponent.pk, {}).get(round_number - 1)
        == OpponentMoveKind.WAIT
    )
    if not is_mindless(profile) and held is not None and not waited_last_round:
        write_plan(opponent, ctx, kind=OpponentMoveKind.WAIT, threat_entry=held)
        return
    write_plan(opponent, ctx, goal_position=advance_to)


def _unaffordable_wall(free: list[Position] | None) -> PositionEdge | None:
    """The breakable wall that is the route's first step when the mover cannot afford it
    this round (a climber with one hop at a wall with a way past it)."""
    if free is None or len(free) < 2:  # noqa: PLR2004 - a route with a first step
        return None
    edge = edge_between(free[0], free[1])
    if edge is None or not is_breakable_barrier(edge):
        return None
    return edge


def write_plan(  # noqa: PLR0913 - one keyword per plan column
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
    *,
    kind: str = OpponentMoveKind.ADVANCE,
    goal_position: Position | None = None,
    barrier_edge: PositionEdge | None = None,
    threat_entry: ThreatPoolEntry | None = None,
) -> None:
    """Write the opponent's move plan, unless it is winding up (then it stands still)."""
    if opponent.pk in ctx.unmatured_windup_opponent_ids:
        return
    write_move_plan(
        opponent,
        ctx.encounter.round_number,
        kind=kind,
        goal_position=goal_position,
        barrier_edge=barrier_edge,
        threat_entry=threat_entry,
    )


# ---------------------------------------------------------------------------
# Retreat (step 1)
# ---------------------------------------------------------------------------


def _retreat_route(
    origin: Position, hostiles: list[Combatant], profile: MovementProfile, memo: ReachMemo
) -> tuple[list[Position] | None, bool]:
    """(route away, whether an enemy reaches it where it stands).

    The route heads for the position farthest from every enemy by path distance (ties
    to the nearer, then the lower pk); None when nowhere is farther than here.
    """
    placed = _placed(hostiles)
    in_reach = any(memo.reaches(pos, origin, StrikeDelivery.MELEE) for _h, pos in placed)
    maps = [
        path_costs_from(pos, traversal=trav)
        for pos, trav in {(pos, _traversal_of(h)) for h, pos in placed}
    ]

    def distance(pk: int) -> int:
        return min((m.get(pk, _UNREACHABLE) for m in maps), default=_UNREACHABLE)

    own = path_costs_from(origin, traversal=profile.traversal)
    best = max(own, key=lambda pk: (distance(pk), -own[pk], -pk))
    if distance(best) <= distance(origin.pk):
        return None, in_reach
    return find_path(origin, lambda n: n.pk == best, traversal=profile.traversal), in_reach


def plan_retreat(opponent: CombatOpponent, ctx: NpcRoundContext) -> bool:
    """A broken opponent's plan. True when its round is settled (it retreats or has fled);
    False when it is cornered and fights instead.

    An opponent off the map, or with no enemy on it, leaves at once (there is nowhere to
    walk), as a broken opponent always did before the map mattered.
    """
    from world.combat.services.npc.npc_targeting import (  # noqa: PLC0415
        _npc_action_target_pool,
    )

    hostiles, _ = _npc_action_target_pool(
        opponent,
        ctx.active_participants,
        ctx.encounter,
        allegiances=ctx.allegiances,
        active_opponents=ctx.all_active,
    )
    profile = opponent.movement_profile
    with mover_origin(opponent, profile) as origin:
        if origin is None or not _placed(hostiles):
            _flee(opponent, announce=False)
            return True
        route, in_reach = _retreat_route(origin, hostiles, profile, ctx.reach_memo)
    if route is None and in_reach:
        return False  # cornered: it fights
    write_plan(
        opponent,
        ctx,
        kind=OpponentMoveKind.RETREAT,
        goal_position=route[-1] if route else None,
    )
    return True


def _flee(opponent: CombatOpponent, *, announce: bool = True) -> None:
    opponent.status = OpponentStatus.FLED
    opponent.save(update_fields=["status"])
    if announce:
        _say(opponent.encounter, NPC_FLEES_NARRATION.format(name=opponent.name))


def _retreat_streak(opponent: CombatOpponent, round_number: int, limit: int) -> int:
    """Rounds in a row the opponent has retreated before this one."""
    kinds = dict(
        CombatOpponentMove.objects.filter(
            opponent=opponent,
            round_number__gte=round_number - limit,
            round_number__lt=round_number,
        ).values_list("round_number", "kind")
    )
    streak = 0
    for past in range(round_number - 1, round_number - limit - 1, -1):
        if kinds.get(past) != OpponentMoveKind.RETREAT:
            break
        streak += 1
    return streak


# ---------------------------------------------------------------------------
# The plan in the opponent's slot
# ---------------------------------------------------------------------------


def run_move_plan(
    opponent: CombatOpponent,
    move: CombatOpponentMove | None,
    attack_rows: list[CombatOpponentAction],
    *,
    on_hop: HopHook | None = None,
) -> SlotMoveResult:
    """Carry out the opponent's move plan in its slot, before any attack row.

    Re-plans against live positions. ``on_hop`` is the waiting strike's arrival trigger;
    a strike that stops the mover ends its move (``result.stopped``).
    """
    result = SlotMoveResult()
    if move is None or opponent.status != OpponentStatus.ACTIVE or opponent.objectdb is None:
        return result
    stopped_hook = _watching(on_hop, result)
    if move.kind == OpponentMoveKind.ADVANCE:
        result.moved = (
            advance_opponent(opponent, move, attack_rows, on_hop=stopped_hook) is not None
        )
    elif move.kind == OpponentMoveKind.SHELTER:
        result.moved = _run_shelter(opponent, move, stopped_hook)
    elif move.kind == OpponentMoveKind.BASH:
        _run_bash(opponent, move, stopped_hook, result)
    elif move.kind == OpponentMoveKind.RETREAT:
        _run_retreat(opponent, move, stopped_hook, result)
    elif move.kind == OpponentMoveKind.WAIT:
        _say(opponent.encounter, NPC_WAITS_NARRATION.format(name=opponent.name))
        result.waited = True
    return result


def _watching(on_hop: HopHook | None, result: SlotMoveResult) -> HopHook | None:
    if on_hop is None:
        return None

    def hook(here: Position, announce: Callable[[], None]) -> bool:
        stopped = on_hop(here, announce)
        result.stopped = result.stopped or stopped
        return stopped

    return hook


def _run_shelter(
    opponent: CombatOpponent, move: CombatOpponentMove, on_hop: HopHook | None
) -> bool:
    """Walk for the planned cover (or, when that is gone, the nearest covered position)."""
    profile = opponent.movement_profile
    goal = move.goal_position
    with mover_origin(opponent, profile) as origin:
        if origin is None:
            return False
        path = None
        if goal is not None:
            path = find_path(origin, lambda n: n.pk == goal.pk, traversal=profile.traversal)
        if path is None:
            path = find_path(
                origin,
                lambda n: n.is_roofed or n.screens_ranged,
                traversal=profile.traversal,
            )
        if path is None:
            return False
        return walk_and_announce(opponent, path, profile, on_hop=on_hop) is not None


def _run_bash(
    opponent: CombatOpponent,
    move: CombatOpponentMove,
    on_hop: HopHook | None,
    result: SlotMoveResult,
) -> None:
    """Walk up to the wall and strike it once. A wall already down: close in instead,
    and strike whoever is in reach with the blow meant for the wall."""
    edge = PositionEdge.objects.select_related(
        "gating_challenge__template", "source_rampart__element_profile"
    ).get(pk=move.barrier_edge_id)
    profile = opponent.movement_profile
    if not is_breakable_barrier(edge) or edge.is_passable:
        advance = CombatOpponentMove(
            opponent=opponent, round_number=move.round_number, kind=OpponentMoveKind.ADVANCE
        )
        result.moved = advance_opponent(opponent, advance, [], on_hop=on_hop) is not None
        if not result.stopped:
            row = _strike_in_reach(opponent, move)
            if row is not None:
                result.attack_rows.append(row)
        return
    ends = {edge.position_a_id, edge.position_b_id}
    with mover_origin(opponent, profile) as origin:
        if origin is None:
            return
        if origin.pk not in ends:
            path = find_path(origin, lambda n: n.pk in ends, traversal=profile.traversal)
            if path is not None:
                result.moved = walk_and_announce(opponent, path, profile, on_hop=on_hop) is not None
        here = target_position(opponent)
    if result.stopped or here is None or here.pk not in ends:
        return
    label = barrier_label(edge)
    entry = move.threat_entry
    _say(opponent.encounter, BATTERS_BARRIER_NARRATION.format(name=opponent.name, barrier=label))
    fell = damage_barrier(edge, bash_chip(entry, opponent), damage_type=entry.damage_type)
    result.bashed = True
    if fell:
        _say(opponent.encounter, BARRIER_GIVES_WAY_NARRATION.format(barrier=_capitalized(label)))


def _capitalized(label: str) -> str:
    return label[:1].upper() + label[1:]


def _strike_in_reach(
    opponent: CombatOpponent, move: CombatOpponentMove
) -> CombatOpponentAction | None:
    """An attack row with the plan's bash entry at a live hostile now in reach, or None."""
    entry = move.threat_entry
    origin = target_position(opponent)
    pool, targeting_participants = _live_target_pool(opponent)
    memo = ReachMemo()
    in_reach = [t for t in pool if memo.reaches(origin, target_position(t), entry.delivery)]
    if not in_reach:
        return None
    chosen = (
        _select_targets(entry, in_reach)
        if targeting_participants
        else _select_opponent_targets(entry, in_reach)
    )
    if not chosen:
        return None
    row = CombatOpponentAction.objects.create(
        opponent=opponent, round_number=move.round_number, threat_entry=entry
    )
    if targeting_participants:
        row.targets.set(chosen)
        row.cached_targets = chosen
        row.cached_opponent_targets = []
    else:
        row.opponent_targets.set(chosen)
        row.cached_targets = []
        row.cached_opponent_targets = chosen
    return row


def _run_retreat(
    opponent: CombatOpponent,
    move: CombatOpponentMove,
    on_hop: HopHook | None,
    result: SlotMoveResult,
) -> None:
    """Back away, then leave the fight when no enemy reaches it or the limit is hit."""
    profile = opponent.movement_profile
    hostiles, _ = _live_target_pool(opponent)
    memo = ReachMemo()
    with mover_origin(opponent, profile) as origin:
        if origin is None:
            _flee(opponent)
            result.fled = True
            return
        route, _in_reach = _retreat_route(origin, hostiles, profile, memo)
        if route is not None:
            result.moved = walk_and_announce(opponent, route, profile, on_hop=on_hop) is not None
    if result.stopped or opponent.status != OpponentStatus.ACTIVE:
        return
    here = target_position(opponent)
    reached = any(memo.reaches(pos, here, StrikeDelivery.MELEE) for _h, pos in _placed(hostiles))
    limit = NpcTacticsConfig.load().retreat_rounds_limit
    streak = _retreat_streak(opponent, move.round_number, limit) + 1
    if not reached or streak >= limit:
        _flee(opponent)
        result.fled = True


# ---------------------------------------------------------------------------
# Physical incapacity: the round log says so
# ---------------------------------------------------------------------------


def narrate_strain(opponent: CombatOpponent) -> None:
    """ "{name} strains against {barrier}." for an opponent that could do nothing at all.

    The barrier is the closed edge nearest it on the way out of the positions it can
    walk to. Said only when there is such an edge; an opponent with nowhere at all to
    go and no wall to name says nothing.
    """
    profile = opponent.movement_profile
    with mover_origin(opponent, profile) as origin:
        if origin is None:
            return
        reachable = path_costs_from(origin, traversal=profile.traversal)
        edges = PositionEdge.objects.filter(position_a__room_id=origin.room_id).select_related(
            "gating_challenge__template", "source_rampart__element_profile"
        )
        boundary = sorted(
            (
                (
                    min(
                        reachable.get(e.position_a_id, _UNREACHABLE),
                        reachable.get(e.position_b_id, _UNREACHABLE),
                    ),
                    e.pk,
                    e,
                )
                for e in edges
                if (e.position_a_id in reachable) != (e.position_b_id in reachable)
            ),
            key=lambda item: (item[0], item[1]),
        )
    if not boundary:
        return
    _say(
        opponent.encounter,
        STRAINS_AGAINST_NARRATION.format(name=opponent.name, barrier=barrier_label(boundary[0][2])),
    )
