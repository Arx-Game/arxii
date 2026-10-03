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
from world.combat.types import WonOverRow
from world.conditions.constants import Allegiance, DurationType

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
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
    """(name, verb, source label) for each WON_OVER opponent, in pk order.

    ``applied_since=encounter.created_at`` (ruling R1, fix round 2): a stale
    higher-precedence hold from before the fight (e.g. an old TURNED) must not
    out-rank a fresh one applied during it (e.g. a Calm) — only instances
    applied during THIS encounter are eligible to designate the label.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
        won_over_verb,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    opponents = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.WON_OVER).order_by(
            "pk"
        )
    )
    by_target = allegiance_instances_for(
        (o.objectdb_id for o in opponents), applied_since=encounter.created_at
    )
    designations: dict[int, ConditionInstance] = {}
    for opponent in opponents:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is not None:
            designations[opponent.pk] = instance

    # A source's ObjectDB pk IS its CharacterSheet pk (shared O2O primary key),
    # so persona_names_for_sheets can be fed the raw source_character ids
    # directly — no CombatParticipant lookup needed, and a source who isn't a
    # CharacterSheet-backed character at all (an NPC ally casting the charm)
    # simply has no entry, falling through to its raw key below.
    source_ids = {
        instance.source_character_id
        for instance in designations.values()
        if instance.source_character_id is not None
    }
    source_names = persona_names_for_sheets(source_ids)

    labels: list[tuple[str, str, str]] = []
    for opponent in opponents:
        instance = designations.get(opponent.pk)
        if instance is None:
            continue  # the hold already ended; nothing to say
        labels.append(
            (
                opponent.name,
                won_over_verb(instance.condition.sets_allegiance),
                _source_label(instance, source_names),
            )
        )
    return labels


def won_over_rows(encounter: CombatEncounter, viewer: CharacterSheet) -> list[WonOverRow]:
    """One row per WON_OVER opponent of the encounter, for the digest (#4091).

    Every WON_OVER opponent is included (not only this viewer's own charms) —
    the action flags are what differ per viewer. ``applied_since=encounter.created_at``
    (ruling R1), same as ``won_over_labels``. Batched: one opponent query, one
    instance query, one persona-name query pair.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
        won_over_verb,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    opponents = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.WON_OVER)
        .select_related("objectdb", "persona")
        .order_by("pk")
    )
    by_target = allegiance_instances_for(
        (o.objectdb_id for o in opponents), applied_since=encounter.created_at
    )
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
    source_names = persona_names_for_sheets(source_ids)

    viewer_char_id = viewer.character_id
    rows: list[WonOverRow] = []
    for opponent in opponents:
        instance = designations.get(opponent.pk)
        if instance is None:
            continue  # the hold already ended; nothing to say

        present = opponent.objectdb_id is not None and opponent.objectdb.location is not None
        nameless = opponent.objectdb_is_ephemeral
        persona_id = opponent.persona_id
        is_source = instance.source_character_id == viewer_char_id
        charmer_is_viewer = (
            is_source and instance.condition.sets_allegiance == Allegiance.ALLY_OF_CASTER
        )
        visible_condition = (
            instance if (instance.condition.is_visible_to_others or is_source) else None
        )

        rows.append(
            WonOverRow(
                opponent_id=opponent.pk,
                name=opponent.name,
                verb=won_over_verb(instance.condition.sets_allegiance),
                source_label=_source_label(instance, source_names),
                nameless=nameless,
                persona_id=persona_id,
                present=present,
                condition=visible_condition,
                holds_until_settled=instance.condition.default_duration_type == DurationType.ROUNDS,
                strength=instance.effective_severity,
                can_bind=charmer_is_viewer and nameless and present,
                can_take_into_service=charmer_is_viewer and persona_id is not None,
                can_send_away=is_source and present,
                can_settle=persona_id is not None and present,
            )
        )
    return rows


def _source_label(instance: ConditionInstance, source_names: dict[int, str]) -> str:
    """The charm/turn/calm source's label: ``"<name>"`` or ``"<name>'s <technique>"``.

    ``<name>`` is the persona this source is CURRENTLY presenting as — the same
    convention the outcome line itself uses (#4091 fix round 2) — batched by the
    caller via ``persona_names_for_sheets``. A source with no persona-mapped
    entry (an NPC ally casting the charm, not a CharacterSheet-backed PC) falls
    back to its raw ``ObjectDB.key``: there is no persona to resolve for it.
    """
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        technique_display_name,
    )

    source = instance.source_character
    if source is None:
        return ""
    label = source_names.get(source.pk, source.key)
    if instance.source_technique_id is not None:
        # What the SOURCE calls their own technique (their personalization hold),
        # never the catalog's raw name (#4091 fix round 2).
        return f"{label}'s {technique_display_name(source, instance.source_technique)}"
    return label
