"""Won-over opponents: the victory check, stamping, and labels (#4091).

A won-over NPC is an enemy wearing an allegiance condition. It never counts as an
enemy standing, it is stamped ``OpponentStatus.WON_OVER`` at victory so the
per-opponent aftermath pool, the digest and the bind window can find it, and its
stored ``allegiance`` is never touched (D4).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.conditions.models import ConditionInstance

logger = logging.getLogger(__name__)


def _active_stored_enemies(encounter: CombatEncounter) -> list[CombatOpponent]:
    return list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            allegiance=CombatAllegiance.ENEMY,
        ).select_related("objectdb")
    )


def hostile_opponents_remain(encounter: CombatEncounter) -> bool:
    """Any ACTIVE enemy not won over during THIS encounter (ruling R1). One query + one."""
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    enemies = _active_stored_enemies(encounter)
    if not enemies:
        return False
    allegiances = effective_allegiances(enemies, applied_since=encounter.created_at)
    return any(allegiances[o.pk] == Allegiance.ENEMY for o in enemies)


def stamp_won_over_opponents(encounter: CombatEncounter) -> list[CombatOpponent]:
    """Stamp every won-over enemy WON_OVER and credit its winner (VICTORY only)."""
    from world.combat.achievement_counters import (  # noqa: PLC0415
        STAT_KEY_OPPONENTS_WON_OVER,
        increment_combat_counter,
    )
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
    )

    enemies = _active_stored_enemies(encounter)
    by_target = allegiance_instances_for(
        (o.objectdb_id for o in enemies), applied_since=encounter.created_at
    )
    won: list[CombatOpponent] = []
    credited: dict[int, int] = {}
    for opponent in enemies:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is None:
            continue
        won.append(opponent)
        if instance.source_character_id is not None:
            credited[instance.source_character_id] = (
                credited.get(instance.source_character_id, 0) + 1
            )
    # Per-row saves, not a bulk .update(): a fight has only a handful of
    # opponents, and a bulk update leaves every cached CombatOpponent instance
    # (including these very `enemies` instances, idmapper-shared with any other
    # holder in this process) reporting the stale status (#4091 fix round 1).
    for opponent in won:
        opponent.status = OpponentStatus.WON_OVER
        opponent.save(update_fields=["status"])
    if credited:
        participants = CombatParticipant.objects.filter(
            encounter=encounter, character_sheet__character_id__in=credited
        ).select_related("character_sheet")
        for participant in participants:
            increment_combat_counter(
                participant.character_sheet,
                STAT_KEY_OPPONENTS_WON_OVER,
                credited[participant.character_sheet.character_id],
            )
    return won


def won_over_labels(encounter: CombatEncounter) -> list[tuple[str, str, str]]:
    """(name, verb, source label) for each WON_OVER opponent, in pk order."""
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
        won_over_verb,
    )

    opponents = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.WON_OVER).order_by(
            "pk"
        )
    )
    by_target = allegiance_instances_for(o.objectdb_id for o in opponents)
    designations: dict[int, ConditionInstance] = {}
    for opponent in opponents:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is not None:
            designations[opponent.pk] = instance

    source_ids = {
        instance.source_character_id
        for instance in designations.values()
        if instance.source_character_id is not None
    }
    source_labels = _participant_labels_by_character_id(encounter, source_ids)

    labels: list[tuple[str, str, str]] = []
    for opponent in opponents:
        instance = designations.get(opponent.pk)
        if instance is None:
            continue  # the hold already ended; nothing to say
        labels.append(
            (
                opponent.name,
                won_over_verb(instance.condition.sets_allegiance),
                _source_label(instance, source_labels),
            )
        )
    return labels


def _participant_labels_by_character_id(
    encounter: CombatEncounter, character_ids: set[int]
) -> dict[int, str]:
    """``str(CombatParticipant)`` per source character id, batched — ONE query.

    This is the exact label the ceremonial OUTCOME line uses for a PC
    (``_broadcast_encounter_outcome``'s ``str(p) for p in participants``), so a
    charm/turn/calm source who is a concealed-identity PC gets the same
    persona-respecting label there and in the won-over clause (#4091 fix round
    2 - a raw ``ObjectDB.key`` must never leak where the outcome line would
    show a persona).
    """
    if not character_ids:
        return {}
    participants = CombatParticipant.objects.filter(
        encounter=encounter, character_sheet__character_id__in=character_ids
    ).select_related("character_sheet__character")
    return {p.character_sheet.character_id: str(p) for p in participants}


def _source_label(instance: ConditionInstance, source_labels: dict[int, str]) -> str:
    source = instance.source_character
    if source is None:
        return ""
    # A PC source resolves to the same str(CombatParticipant) label the outcome
    # line uses; a non-participant source (an NPC ally, say) falls back to its
    # raw key — there is no persona-respecting label to match there.
    label = source_labels.get(source.pk, source.key)
    if instance.source_technique_id is not None:
        return f"{label}'s {instance.source_technique.name}"
    return label
