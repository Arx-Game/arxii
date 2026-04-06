"""Service functions for combat encounter lifecycle."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

from world.combat.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
    EncounterStatus,
    OpponentStatus,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    ThreatPool,
    ThreatPoolEntry,
)
from world.combat.types import OpponentDamageResult, ParticipantDamageResult


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    max_health: int,
    covenant_role: str | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant with health equal to max_health."""
    return CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        health=max_health,
        max_health=max_health,
        covenant_role=covenant_role,
    )


def add_opponent(  # noqa: PLR0913 - opponent creation requires all stat fields
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    max_health: int,
    threat_pool: ThreatPool,
    description: str = "",
    soak_value: int = 0,
    probing_threshold: int | None = None,
) -> CombatOpponent:
    """Create a CombatOpponent with health equal to max_health."""
    return CombatOpponent.objects.create(
        encounter=encounter,
        name=name,
        tier=tier,
        max_health=max_health,
        health=max_health,
        threat_pool=threat_pool,
        description=description,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
    )


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance round_number by 1 and set status to DECLARING.

    Uses select_for_update to prevent concurrent calls.
    """
    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    enc.round_number += 1
    enc.status = EncounterStatus.DECLARING
    enc.save(update_fields=["round_number", "status"])
    # Refresh the caller's instance so it reflects the new state.
    encounter.refresh_from_db()


def _get_eligible_entries(
    opponent: CombatOpponent,
) -> list[ThreatPoolEntry]:
    """Return threat pool entries eligible for this opponent's current state."""
    if not opponent.threat_pool_id:
        return []

    entries: list[ThreatPoolEntry] = list(
        ThreatPoolEntry.objects.filter(pool_id=opponent.threat_pool_id)
    )

    eligible: list[ThreatPoolEntry] = []
    for entry in entries:
        # Filter by minimum_phase
        if entry.minimum_phase is not None and entry.minimum_phase > opponent.current_phase:
            continue

        # Filter by cooldown — check if used in recent rounds
        if entry.cooldown_rounds is not None:
            earliest_allowed = max(
                1,
                opponent.encounter.round_number - entry.cooldown_rounds + 1,
            )
            recently_used = CombatOpponentAction.objects.filter(
                opponent=opponent,
                threat_entry=entry,
                round_number__gte=earliest_allowed,
            ).exists()
            if recently_used:
                continue

        eligible.append(entry)

    return eligible


def _select_targets(
    entry: ThreatPoolEntry,
    active_participants: list[CombatParticipant],
) -> list[CombatParticipant]:
    """Select targets for a threat pool entry from active participants."""
    if not active_participants:
        return []

    mode = entry.targeting_mode
    selection = entry.target_selection

    if mode == TargetingMode.ALL:
        return list(active_participants)

    count = 1
    if mode == TargetingMode.MULTI:
        count = entry.target_count or 1

    count = min(count, len(active_participants))

    if selection == TargetSelection.LOWEST_HEALTH:
        sorted_by_health = sorted(active_participants, key=lambda p: p.health)
        return sorted_by_health[:count]

    if selection == TargetSelection.RANDOM:
        return random.sample(active_participants, count)

    # SPECIFIC_ROLE and HIGHEST_THREAT: placeholder — pick first active participants
    return list(active_participants[:count])


def select_npc_actions(
    encounter: CombatEncounter,
) -> list[CombatOpponentAction]:
    """Select and create NPC actions for the current round.

    For each active opponent with a threat pool, picks a weighted-random
    entry from eligible threat pool entries and assigns targets.
    """
    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).exclude(threat_pool__isnull=True)
    )

    active_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
    )

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        eligible = _get_eligible_entries(opponent)
        if not eligible:
            continue

        weights = [e.weight for e in eligible]
        chosen = random.choices(eligible, weights=weights, k=1)[0]  # noqa: S311

        targets = _select_targets(chosen, active_participants)

        action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=encounter.round_number,
            threat_entry=chosen,
        )
        action.targets.set(targets)
        actions.append(action)

    return actions


def apply_damage_to_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, accounting for soak and probing.

    All raw damage (even fully soaked) contributes to probing. Only damage
    that exceeds soak actually reduces health.
    """
    effective_soak = 0 if bypass_soak else opponent.soak_value
    damage_through = max(0, raw_damage - effective_soak)
    probing_increment = max(0, raw_damage)

    opponent.health -= damage_through
    opponent.probing_current += probing_increment

    defeated = opponent.health <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED

    opponent.save(update_fields=["health", "probing_current", "status"])

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
    )


def apply_damage_to_participant(
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
) -> ParticipantDamageResult:
    """Apply damage to a PC participant and report threshold crossings.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.
    """
    participant.health -= damage
    health_after = participant.health

    if participant.max_health > 0:
        health_pct = max(0.0, health_after / participant.max_health)
    else:
        health_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = damage > (participant.max_health * PERMANENT_WOUND_THRESHOLD)

    if force_death:
        participant.status = ParticipantStatus.DYING
        participant.dying_final_round = True

    participant.save(update_fields=["health", "status", "dying_final_round"])

    return ParticipantDamageResult(
        damage_dealt=damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
    )
