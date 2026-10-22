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
        .select_related("threat_pool", "objectdb")
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

    _apply_aggro_conditions(opponents, active_participants, threat_maps, shield_participant_ids)
    provokers = _provoking_participant_ids(opponents, active_participants)

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
                provoker_participant_id=provokers.get(opponent.pk),
                allegiances=allegiances,
                active_opponents=all_active,
            )
        )

    return actions


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
    provoker_participant_id: int | None = None,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> list[CombatOpponentAction]:
    """Create one opponent's NPC action rows for the current round.

    Returns the created actions, or an empty list when the opponent skips the
    round — no eligible (off-cooldown) threat entry, or the empty-pool guard:
    no valid target (a #1584 ALLY summon or #4091 charmed/turned NPC with no
    live hostile, or a #1590 calmed/neutral opponent).

    ``provoker_participant_id`` is the participant whose forces_attack_on_source condition
    sits on this opponent (#4584). It narrows the pool to that participant after the lock
    check: an engagement lock that narrowed the pool wins, and a provoker outside the pool
    leaves it as it was. Player characters ignore the flag because PCs choose their own
    targets; charmed, turned and summoned opponents ignore it because they do not target the
    PC side (``targeting_participants`` is false).
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
    if targeting_participants:
        target_pool = _narrow_to_locked_or_provoker(
            target_pool, locked_participant_id, provoker_participant_id
        )

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
