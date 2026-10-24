"""Selecting NPC opponent actions for a round."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.combat.constants import (
    EngagementLockStatus,
    OpponentMoveKind,
    OpponentStatus,
    OpponentTier,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    EngagementLock,
    PendingOpponentAttack,
    ThreatPoolEntry,
    ThreatRecord,
)
from world.combat.services.damage.swarm import swarm_attack_count
from world.combat.services.npc.companion_orders import _COMPANION_HOLD, _apply_companion_order
from world.combat.services.npc.npc_attack import _execute_npc_attack
from world.combat.services.npc.npc_cooldowns import _batch_fetch_cooldown_data
from world.combat.services.npc.npc_movement import (
    ReachMemo,
    mover_origin,
    nearest_hostile_position,
    reachable_pools,
    strike_pool_key,
    write_move_plan,
)
from world.combat.services.npc.npc_tactics import (
    build_tactics_inputs,
    grounding_strike,
    plan_approach,
    plan_retreat,
    plannable_opponents,
    shelter_goal,
    unanswerable_attackers,
    usable_entries,
    write_grounding_attack,
    write_plan,
)
from world.combat.services.npc.npc_targeting import (
    _get_eligible_entries,
    _npc_action_target_pool,
    _targetable_participants,
)
from world.conditions.constants import Allegiance
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.combat.types import TacticsInputs


@dataclass
class NpcRoundContext:
    """Everything NPC planning reads for one round, batch-fetched once (#4607).

    Built by ``_build_npc_round_context`` and shared by ``select_npc_actions`` and
    ``ensure_opponent_plans`` so neither duplicates the batch prefetches.
    """

    encounter: CombatEncounter
    opponents: list[CombatOpponent]
    all_active: list[CombatOpponent]
    allegiances: dict[int, Allegiance]
    entries_by_pool: dict[int, list[ThreatPoolEntry]]
    recently_used_by_opponent: dict[int, set[int]]
    active_participants: list[CombatParticipant]
    threat_maps: dict[int, dict[int, int]]
    active_locks_by_opponent: dict[int, int]
    shield_participant_ids: set[int]
    provokers: dict[int, int]
    unmatured_windup_opponent_ids: set[int]
    tactics: TacticsInputs
    reach_memo: ReachMemo = field(default_factory=ReachMemo)


def _plannable_opponents(encounter: CombatEncounter) -> list[CombatOpponent]:
    """ACTIVE opponents with a threat pool that are not duel mirrors (``plannable_opponents``)."""
    return list(
        plannable_opponents(CombatOpponent.objects.filter(encounter=encounter)).select_related(
            "threat_pool", "objectdb"
        )
    )


def _build_npc_round_context(
    encounter: CombatEncounter,
    opponents: list[CombatOpponent],
) -> NpcRoundContext:
    """Batch-fetch the round's NPC planning inputs for ``opponents``."""
    # Effective allegiance for every active opponent, computed once per round
    # (#4091) — includes opponents with no threat pool (e.g. mirrored bosses)
    # so a charmed/turned attacker's hostile pool sees the whole encounter.
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    all_active = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.ACTIVE)
    )
    allegiances = effective_allegiances(all_active)

    # Batch-prefetch all threat pool entries for all opponent pools
    pool_ids = {o.threat_pool_id for o in opponents if o.threat_pool_id}
    all_entries = list(ThreatPoolEntry.objects.filter(pool_id__in=pool_ids))
    entries_by_pool: dict[int, list[ThreatPoolEntry]] = defaultdict(list)
    for entry in all_entries:
        entries_by_pool[entry.pool_id].append(entry)

    recently_used_by_opponent = _batch_fetch_cooldown_data(
        opponents,
        entries_by_pool,
        all_entries,
        encounter.round_number,
    )

    active_participants = _targetable_participants(encounter)

    # Batch-prefetch ThreatRecord data for HIGHEST_THREAT/SPECIFIC_ROLE (#2020)
    active_participant_ids = [p.pk for p in active_participants]
    threat_maps: dict[int, dict[int, int]] = defaultdict(dict)
    if active_participant_ids:
        for tr in ThreatRecord.objects.filter(
            opponent__in=opponents,
            participant_id__in=active_participant_ids,
        ):
            threat_maps[tr.opponent_id][tr.participant_id] = tr.threat_value

    # Batch-prefetch active EngagementLocks for lock narrowing (#2020)
    active_locks_by_opponent: dict[int, int] = {}
    for lock in EngagementLock.objects.filter(
        encounter=encounter,
        opponent__in=opponents,
        status=EngagementLockStatus.ACTIVE,
    ).values("opponent_id", "participant_id"):
        active_locks_by_opponent[lock["opponent_id"]] = lock["participant_id"]

    # Batch-prefetch SHIELD-axis (blend weight > 0) participant IDs for SPECIFIC_ROLE (#2020)
    from world.covenants.constants import RoleArchetype  # noqa: PLC0415
    from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

    shield_participant_ids: set[int] = set()
    for p in active_participants:
        role = precedence_role_for_combat(p.character_sheet)
        if role is not None and role.blend_weight_for(RoleArchetype.SHIELD) > 0:
            shield_participant_ids.add(p.pk)

    _apply_aggro_conditions(opponents, active_participants, threat_maps, shield_participant_ids)

    return NpcRoundContext(
        encounter=encounter,
        opponents=opponents,
        all_active=all_active,
        allegiances=allegiances,
        entries_by_pool=entries_by_pool,
        recently_used_by_opponent=recently_used_by_opponent,
        active_participants=active_participants,
        threat_maps=threat_maps,
        active_locks_by_opponent=active_locks_by_opponent,
        shield_participant_ids=shield_participant_ids,
        provokers=_provoking_participant_ids(opponents, active_participants),
        unmatured_windup_opponent_ids=_unmatured_windup_opponent_ids(encounter, opponents),
        tactics=build_tactics_inputs(encounter, opponents, all_active, entries_by_pool),
    )


def _unmatured_windup_opponent_ids(
    encounter: CombatEncounter, opponents: list[CombatOpponent]
) -> set[int]:
    """Opponents still winding up when the round is planned (the telegraph is their action).

    Includes a wind-up that lands this round: maturation runs after planning, and the blow
    comes from where the opponent stands, so a fighter who stepped out of reach makes it
    miss instead of being chased down (#4607).
    """
    return set(
        PendingOpponentAttack.objects.filter(
            opponent__in=opponents,
            resolves_round__gte=encounter.round_number,
        ).values_list("opponent_id", flat=True)
    )


def select_npc_actions(
    encounter: CombatEncounter,
) -> list[CombatOpponentAction]:
    """Select and create NPC actions for the current round.

    For each active opponent with a threat pool, picks a weighted-random
    entry from eligible threat pool entries and assigns targets. Targeting is
    allegiance-aware (#1590, #4091, ADR-0058 as amended by ADR-4091): a charmed
    opponent (``ALLY_OF_CASTER``) targets ENEMY/TURNED opponents, a turned
    opponent (``TURNED``) targets its own former (stored-ENEMY) side, and a
    calmed opponent (``NEUTRAL``) holds and takes no action; an opponent left
    with no valid targets skips the round.

    Every planned opponent also gets its one ``CombatOpponentMove`` plan for the
    round (#4607, ``plan_opponent_round``). Returns the attack rows only.

    Raises ValueError if the encounter is not in DECLARING status.
    """
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot select NPC actions: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Auto-lock formation: check threat thresholds before NPC targeting (#2020).
    from world.combat.engagement_locks import check_auto_lock_formation  # noqa: PLC0415

    check_auto_lock_formation(encounter)

    opponents = _plannable_opponents(encounter)
    if not opponents:
        return []

    ctx = _build_npc_round_context(encounter, opponents)
    actions: list[CombatOpponentAction] = []
    for opponent in opponents:
        actions.extend(plan_opponent_round(opponent, ctx))
    return actions


def ensure_opponent_plans(encounter: CombatEncounter) -> None:
    """Give every plannable opponent still without a plan this round its plan (#4607).

    An ACTIVE, non-mirror opponent with a threat pool that has no attack row, no move
    row and no unmatured wind-up this round is planned in full (``plan_opponent_round``).
    One that already has attack rows (staff or a simulation selected them) but no move
    row gets only its ADVANCE row. An opponent with an unmatured wind-up is left alone:
    the telegraph is its action. Idempotent; a partial prior selection never leaves an
    opponent idle. Calmed opponents and companion HOLD orders still write nothing, as
    in ``plan_opponent_round``.
    """
    opponents = _plannable_opponents(encounter)
    if not opponents:
        return
    round_number = encounter.round_number
    with_attacks = set(
        CombatOpponentAction.objects.filter(
            opponent__in=opponents, round_number=round_number
        ).values_list("opponent_id", flat=True)
    )
    with_moves = set(
        CombatOpponentMove.objects.filter(
            opponent__in=opponents, round_number=round_number
        ).values_list("opponent_id", flat=True)
    )
    winding_up = _unmatured_windup_opponent_ids(encounter, opponents)
    unplanned: list[CombatOpponent] = []
    for opponent in opponents:
        if opponent.pk in with_moves or opponent.pk in winding_up:
            continue
        if opponent.pk in with_attacks:
            write_move_plan(opponent, round_number)
        else:
            unplanned.append(opponent)
    if not unplanned:
        return
    ctx = _build_npc_round_context(encounter, unplanned)
    for opponent in unplanned:
        plan_opponent_round(opponent, ctx)


def _apply_aggro_conditions(
    opponents: list[CombatOpponent],
    active_participants: list[CombatParticipant],
    threat_maps: dict[int, dict[int, int]],
    shield_participant_ids: set[int],
) -> None:
    """Fold draws_aggro conditions into this round's target selection (#4572).

    A PC carrying a draws_aggro condition counts its summed aggro_priority as extra
    threat with every opponent (an entry is created where no ThreatRecord exists, so
    HIGHEST_THREAT does not fall back to rotation) and joins the SPECIFIC_ROLE preferred
    set beside shield-role PCs. Preferred-set membership is "carries an active draws_aggro
    condition" (even at aggro_priority 0); the priority sum only feeds threat. Aggro is read
    for player characters only because NPC targeting picks among PC participants.
    Selection-time only: no ThreatRecord is written, and an engagement lock still narrows the
    pool afterwards.
    """
    from world.conditions.services import (  # noqa: PLC0415
        aggro_priority_by_target,
        draws_aggro_target_ids,
    )

    characters = [p.character_sheet.character for p in active_participants]
    aggro_by_character = aggro_priority_by_target(characters)
    drawing_aggro = draws_aggro_target_ids(characters)
    aggro_by_participant = {
        p.pk: aggro_by_character[p.character_sheet.character.pk]
        for p in active_participants
        if p.character_sheet.character.pk in aggro_by_character
    }
    for opponent in opponents:
        opponent_threat = threat_maps[opponent.pk]
        for participant_id, aggro in aggro_by_participant.items():
            opponent_threat[participant_id] = opponent_threat.get(participant_id, 0) + aggro
    shield_participant_ids.update(
        p.pk for p in active_participants if p.character_sheet.character.pk in drawing_aggro
    )


def _provoking_participant_ids(
    opponents: list[CombatOpponent],
    active_participants: list[CombatParticipant],
) -> dict[int, int]:
    """Map each provoked opponent to the participant that provoked it (#4584).

    One query for every opponent. The condition's source is mapped through
    ``active_participants``, so a source that is down, untargetable, out of the fight or
    not a player character is simply absent, and the opponent chooses as it normally would.
    """
    from world.conditions.services import provoking_source_by_target  # noqa: PLC0415

    bearers = [o.objectdb for o in opponents if o.objectdb_id is not None]
    source_by_bearer = provoking_source_by_target(bearers)
    if not source_by_bearer:
        return {}
    participant_by_character = {p.character_sheet.character.pk: p.pk for p in active_participants}
    return {
        o.pk: participant_by_character[source_by_bearer[o.objectdb_id]]
        for o in opponents
        if o.objectdb_id in source_by_bearer
        and source_by_bearer[o.objectdb_id] in participant_by_character
    }


def _narrow_to_locked_or_provoker(
    target_pool: list[CombatParticipant],
    locked_participant_id: int | None,
    provoker_participant_id: int | None,
) -> list[CombatParticipant]:
    """Narrow a participant pool to the engagement-locked PC (#2020), else the provoker (#4584).

    An active lock wins over a provoke. Either id outside the pool leaves the pool as it was.
    """
    for participant_id in (locked_participant_id, provoker_participant_id):
        if participant_id is None:
            continue
        narrowed = [p for p in target_pool if p.pk == participant_id]
        if narrowed:
            return narrowed
    return target_pool


def plan_opponent_round(
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
) -> list[CombatOpponentAction]:
    """Plan one opponent's round: its attack rows and its one move plan (#4607, #4609).

    Returns the created attack rows. The move plan comes from the tactics ladder
    (``npc_tactics``, see its module docstring): a broken opponent retreats over the
    map (RETREAT) unless it is cornered; one hit by an attacker it cannot answer makes
    for cover (SHELTER) and still strikes what it reaches there; one with nobody in reach
    advances, bashes a wall in its way, or waits once for an opening. Writes no row at
    all when the opponent is calmed (NEUTRAL holds by design, #1590) or holds on a
    companion HOLD order (#1921), and no move row while it is winding up, including a
    wind-up that lands this round (the telegraph is its action and standing still is
    the tell).

    Attack rows go only at targets the opponent can strike THIS round: reachable from
    its position within ``speed_hops`` for the chosen entry's delivery, and from where it
    stands for a wind-up entry (``reachable_pools``); unplaced combatants count as
    reachable. With no eligible entry (all on cooldown) it writes the ADVANCE row only,
    hinting the nearest hostile's position. A summon with no live hostile left gets the
    ADVANCE row and no attack. A cunning or tactical opponent spends its first attack on
    a grounding entry at a flier hitting it that nothing else it has can reach (a mindless
    one never uses grounding entries).

    ``ctx.provokers`` maps an opponent to the participant whose forces_attack_on_source
    condition sits on it (#4584). It narrows the pool to that participant after the lock
    check: an engagement lock that narrowed the pool wins, and a provoker outside the pool
    leaves it as it was. Player characters ignore the flag because PCs choose their own
    targets; charmed, turned and summoned opponents ignore it because they do not target the
    PC side (``targeting_participants`` is false).
    """
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    # Break: a broken opponent backs away over the map and leaves (#2015, #4609).
    if morale_state_for(opponent) == OpponentMoraleState.BREAK and plan_retreat(opponent, ctx):
        return []

    if ctx.allegiances.get(opponent.pk, Allegiance.ENEMY) == Allegiance.NEUTRAL:
        return []

    resolved = _round_target_pool(opponent, ctx)
    if resolved is None:
        return []  # a companion HOLD order
    target_pool, targeting_participants = resolved

    profile = opponent.movement_profile
    grounding = ctx.tactics.grounding_entry_ids
    pool_entries = ctx.entries_by_pool.get(opponent.threat_pool_id, [])
    usable = usable_entries(pool_entries, profile, grounding)
    eligible = usable_entries(
        _get_eligible_entries(
            opponent,
            pool_entries,
            ctx.recently_used_by_opponent.get(opponent.pk, set()),
        ),
        profile,
        grounding,
    )
    with mover_origin(opponent, profile) as origin:
        pools = reachable_pools(
            origin,
            target_pool,
            {strike_pool_key(e) for e in eligible},
            profile=profile,
            memo=ctx.reach_memo,
        )
        strikeable = [e for e in eligible if pools[strike_pool_key(e)]]
        attackers = unanswerable_attackers(
            opponent, origin, usable, profile=profile, inputs=ctx.tactics, memo=ctx.reach_memo
        )
        shelter = shelter_goal(
            opponent,
            origin,
            attackers,
            profile=profile,
            allies=ctx.all_active,
            memo=ctx.reach_memo,
        )
        if not strikeable:
            _plan_with_no_one_in_reach(
                opponent, ctx, origin, target_pool, eligible, usable, shelter=shelter
            )
            return []
        grounder = grounding_strike(
            origin,
            ctx.tactics.aimed_at.get(opponent.pk, []),
            eligible,
            usable,
            profile=profile,
            inputs=ctx.tactics,
            memo=ctx.reach_memo,
        )

    in_reach = list({t.pk: t for pool in pools.values() for t in pool}.values())
    actions: list[CombatOpponentAction] = []
    first_attack = 0
    if grounder is not None:
        entry, flier = grounder
        actions.append(write_grounding_attack(opponent, ctx.encounter, entry, flier))
        first_attack = 1
    declared_windup = False
    for attack_index in range(first_attack, _attack_count(opponent, len(in_reach))):
        declared_windup |= _execute_npc_attack(
            opponent=opponent,
            eligible=strikeable,
            encounter=ctx.encounter,
            target_pool=in_reach,
            targeting_participants=targeting_participants,
            rotation=attack_index,
            threat_map=ctx.threat_maps.get(opponent.pk),
            shield_participant_ids=ctx.shield_participant_ids,
            actions=actions,
            pools=pools,
        )

    if not declared_windup:
        if shelter is not None:
            write_plan(opponent, ctx, kind=OpponentMoveKind.SHELTER, goal_position=shelter)
        else:
            _write_advance_unless_winding_up(opponent, ctx)
    return actions


def _round_target_pool(opponent: CombatOpponent, ctx: NpcRoundContext) -> tuple[list, bool] | None:
    """The opponent's hostiles this round, narrowed by a lock, a provoke or a companion
    order; None when a companion HOLD order keeps it out of the round."""
    target_pool, targeting_participants = _npc_action_target_pool(
        opponent,
        ctx.active_participants,
        ctx.encounter,
        allegiances=ctx.allegiances,
        active_opponents=ctx.all_active,
    )
    # Lock narrowing: if an active EngagementLock exists, narrow to the locked PC (#2020).
    if targeting_participants:
        target_pool = _narrow_to_locked_or_provoker(
            target_pool,
            ctx.active_locks_by_opponent.get(opponent.pk),
            ctx.provokers.get(opponent.pk),
        )
    # --- Companion order integration (#1921) ---
    # An ALLY summon with a CompanionOrder may override its target or skip.
    companion_result = _apply_companion_order(opponent, ctx.encounter.round_number, target_pool)
    if companion_result is _COMPANION_HOLD:
        return None
    if isinstance(companion_result, list):
        target_pool = companion_result
    return target_pool, targeting_participants


def _attack_count(opponent: CombatOpponent, targets_in_reach: int) -> int:
    """How many attack rows the opponent writes: a swarm's by its bodies, else its actions."""
    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        return swarm_attack_count(
            opponent.swarm_count, opponent.bodies_per_attack or 1, targets_in_reach
        )
    return opponent.actions_per_round


def _plan_with_no_one_in_reach(  # noqa: PLR0913 - the ladder's per-opponent inputs
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
    origin: Position | None,
    target_pool: list,
    eligible: list[ThreatPoolEntry],
    usable: list[ThreatPoolEntry],
    *,
    shelter: Position | None,
) -> None:
    """The move plan of an opponent no hostile is in reach of this round."""
    profile = opponent.movement_profile
    if shelter is not None:
        write_plan(opponent, ctx, kind=OpponentMoveKind.SHELTER, goal_position=shelter)
    elif eligible:
        plan_approach(opponent, ctx, origin, target_pool, eligible, usable, profile=profile)
    else:
        # All on cooldown: close in on the nearest hostile's own position.
        goal = nearest_hostile_position(origin, target_pool, profile)
        _write_advance_unless_winding_up(opponent, ctx, goal_position=goal)


def _write_advance_unless_winding_up(
    opponent: CombatOpponent,
    ctx: NpcRoundContext,
    *,
    goal_position: Position | None = None,
) -> None:
    """Write the opponent's ADVANCE plan, unless it is winding up (then it stands still)."""
    if opponent.pk not in ctx.unmatured_windup_opponent_ids:
        write_move_plan(opponent, ctx.encounter.round_number, goal_position=goal_position)
