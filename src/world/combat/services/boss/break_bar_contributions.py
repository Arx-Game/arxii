"""Who contributed to a break and how."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ClashFlavor, ClashResolution, EngagementLockStatus
from world.combat.models import (
    Clash,
    ClashContribution,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    EngagementLock,
)
from world.combat.services.encounter.behavior_conditions import _new_behavior_altering_conditions

if TYPE_CHECKING:
    from datetime import datetime


def _pc_lock_hold_contributors(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
) -> list[int | None]:
    """Participant PKs (or a lone ``None``) crediting a HOLD event per LOCK win this round.

    A LOCK-flavor Clash against *boss* that resolved PC_DECISIVE/PC_MARGINAL this
    round is a PC-side win. Contributors are the PCs with a ``ClashContribution``
    on that clash's resolving-round ``ClashRound`` — falling back to a single
    unattributed (``None``) entry when the clash resolved with no PC contribution
    row (e.g. a pure-abandonment-adjacent edge case).
    """
    won_locks = Clash.objects.filter(
        encounter=encounter,
        npc_opponent=boss,
        flavor=ClashFlavor.LOCK,
        resolved_round=round_number,
        resolution__in=(ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL),
    )
    contributor_ids: list[int | None] = []
    for clash in won_locks:
        character_ids = ClashContribution.objects.filter(
            clash_round__clash=clash,
            clash_round__round_number=round_number,
        ).values_list("character_id", flat=True)
        participant_ids = list(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet_id__in=character_ids,
            ).values_list("pk", flat=True)
        )
        if participant_ids:
            contributor_ids.extend(participant_ids)
        else:
            contributor_ids.append(None)
    return contributor_ids


def _boss_new_debuff_events(
    boss: CombatOpponent,
    encounter: CombatEncounter,
    round_started_at: datetime | None,
) -> list[int | None]:
    """Participant PKs (or ``None``) crediting a DEBUFF event for *boss* this round."""
    if boss.objectdb_id is None or round_started_at is None:
        return []
    return [
        _participant_id_for_objectdb(encounter, inst.source_character_id)
        for inst in _new_behavior_altering_conditions(boss.objectdb_id, round_started_at)
    ]


def _newly_suppressed_lieutenants(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    round_started_at: datetime | None,
) -> list[tuple[CombatOpponent, int | None]]:
    """Lieutenants reinforcing *boss* that became suppressed this round (#2642).

    Round-scoped to the two events with a clean "this round" signal: a new
    behavior-altering condition landing on the lieutenant's ObjectDB
    (``applied_at`` within this round's window), or a new ACTIVE
    ``EngagementLock`` pinning the lieutenant (``started_round == round_number``).
    Status/morale-driven suppression has no per-round timestamp in the schema
    and is not used as a SUPPRESSION trigger — a documented approximation
    (#2642); it still counts toward the lieutenant gate via ``_active_reinforcer_count``.
    """
    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss))
    if not lieutenants:
        return []

    events: list[tuple[CombatOpponent, int | None]] = []
    for lieutenant in lieutenants:
        if lieutenant.objectdb_id is not None and round_started_at is not None:
            for inst in _new_behavior_altering_conditions(lieutenant.objectdb_id, round_started_at):
                participant_id = _participant_id_for_objectdb(encounter, inst.source_character_id)
                events.append((lieutenant, participant_id))
        new_lock = EngagementLock.objects.filter(
            opponent=lieutenant,
            status=EngagementLockStatus.ACTIVE,
            started_round=round_number,
        ).first()
        if new_lock is not None:
            events.append((lieutenant, new_lock.participant_id))
    return events


def _participant_id_for_objectdb(encounter: CombatEncounter, objectdb_id: int | None) -> int | None:
    """Resolve an ObjectDB id to the ``CombatParticipant`` pk fielding it in *encounter*."""
    if objectdb_id is None:
        return None
    return (
        CombatParticipant.objects.filter(
            encounter=encounter, character_sheet__character_id=objectdb_id
        )
        .values_list("pk", flat=True)
        .first()
    )
