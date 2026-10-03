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
    if won:
        CombatOpponent.objects.filter(pk__in=[o.pk for o in won]).update_with_reason(
            reason="issue #4091: won-over opponents stop counting as hostile",
            status=OpponentStatus.WON_OVER,
        )
        for opponent in won:  # keep identity-mapped instances in step with the row
            opponent.status = OpponentStatus.WON_OVER
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
    labels: list[tuple[str, str, str]] = []
    for opponent in opponents:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is None:
            continue  # the hold already ended; nothing to say
        labels.append(
            (
                opponent.name,
                won_over_verb(instance.condition.sets_allegiance),
                _source_label(instance),
            )
        )
    return labels


def _source_label(instance: ConditionInstance) -> str:
    source = instance.source_character
    if source is None:
        return ""
    if instance.source_technique_id is not None:
        return f"{source.key}'s {instance.source_technique.name}"
    return source.key
