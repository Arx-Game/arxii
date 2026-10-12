"""Selecting NPC opponent actions for a round."""

from __future__ import annotations

from collections import defaultdict

from world.combat.constants import (
    EngagementLockStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    EngagementLock,
    ThreatPoolEntry,
    ThreatRecord,
)
from world.combat.services.damage.swarm import swarm_attack_count
from world.combat.services.npc.companion_orders import _COMPANION_HOLD, _apply_companion_order
from world.combat.services.npc.npc_attack import _execute_npc_attack
from world.combat.services.npc.npc_cooldowns import _batch_fetch_cooldown_data
from world.combat.services.npc.npc_targeting import _get_eligible_entries, _npc_action_target_pool
from world.conditions.constants import Allegiance
from world.scenes.constants import RoundStatus


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

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(threat_pool__isnull=True)
        .exclude(mirrors_participant_id__isnull=False)
        .select_related("threat_pool")
    )

    if not opponents:
        return []

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

    # Design: NPCs target PCs who can still act (not dead, not incapacitated).
    # Unconscious PCs (awareness 0) are "down" and not picked as targets; a
    # dying-but-conscious PC remains in the fight and is targetable. can_act is
    # the same coarse agency gate used for declaration eligibility.
    # Intangible PCs (incorporeal, sunk, phased) are also excluded (#1584 Task 8).
    from world.conditions.services import is_untargetable  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    candidate_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    active_participants = [
        p
        for p in candidate_participants
        if can_act(p.character_sheet) and not is_untargetable(p.character_sheet.character)
    ]

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

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        pool_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_used = recently_used_by_opponent.get(opponent.pk, set())
        actions.extend(
            _build_opponent_round_actions(
                opponent,
                pool_entries,
                cooldown_used,
                active_participants,
                encounter,
                threat_map=threat_maps.get(opponent.pk),
                shield_participant_ids=shield_participant_ids,
                locked_participant_id=active_locks_by_opponent.get(opponent.pk),
                allegiances=allegiances,
                active_opponents=all_active,
            )
        )

    return actions


def _build_opponent_round_actions(  # noqa: PLR0913
    opponent: CombatOpponent,
    pool_entries: list[ThreatPoolEntry],
    cooldown_used: set[int],
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,
    *,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
    locked_participant_id: int | None = None,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> list[CombatOpponentAction]:
    """Create one opponent's NPC action rows for the current round.

    Returns the created actions, or an empty list when the opponent skips the
    round — no eligible (off-cooldown) threat entry, or the empty-pool guard:
    no valid target (a #1584 ALLY summon or #4091 charmed/turned NPC with no
    live hostile, or a #1590 calmed/neutral opponent).
    """
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    # Break: a broken opponent flees — set FLED and skip the round (#2015).
    if morale_state_for(opponent) == OpponentMoraleState.BREAK:
        opponent.status = OpponentStatus.FLED
        opponent.save(update_fields=["status"])
        return []

    eligible = _get_eligible_entries(opponent, pool_entries, cooldown_used)
    if not eligible:
        return []

    target_pool, targeting_participants = _npc_action_target_pool(
        opponent,
        active_participants,
        encounter,
        allegiances=allegiances,
        active_opponents=active_opponents,
    )
    if not target_pool:
        return []

    # Lock narrowing: if an active EngagementLock exists, narrow to the locked PC (#2020).
    if locked_participant_id is not None and targeting_participants:
        locked_pool = [p for p in target_pool if p.pk == locked_participant_id]
        if locked_pool:
            target_pool = locked_pool

    # --- Companion order integration (#1921) ---
    # An ALLY summon with a CompanionOrder may override its target or skip.
    companion_result = _apply_companion_order(opponent, encounter.round_number, target_pool)
    if companion_result is _COMPANION_HOLD:
        return []
    if isinstance(companion_result, list):
        target_pool = companion_result

    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        n_attacks = swarm_attack_count(
            opponent.swarm_count,
            opponent.bodies_per_attack or 1,
            len(target_pool),
        )
    else:
        n_attacks = opponent.actions_per_round

    actions: list[CombatOpponentAction] = []
    for attack_index in range(n_attacks):
        _execute_npc_attack(
            opponent=opponent,
            eligible=eligible,
            encounter=encounter,
            target_pool=target_pool,
            targeting_participants=targeting_participants,
            rotation=attack_index,
            threat_map=threat_map,
            shield_participant_ids=shield_participant_ids,
            actions=actions,
        )

    return actions
