"""Won-over opponents: the victory check, stamping, and labels (#4091).

A won-over NPC is an enemy wearing an allegiance condition. It never counts as an
enemy standing, it is stamped ``OpponentStatus.WON_OVER`` at victory so the
per-opponent aftermath pool, the digest and the bind window can find it, and its
stored ``allegiance`` is never touched (D4).
"""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import TYPE_CHECKING

from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.types import WonOverRow, WonOverSnapshot
from world.conditions.constants import Allegiance, DurationType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

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


def _window_open(opponent: CombatOpponent, instances: list[ConditionInstance]) -> bool:
    """Pure predicate: does one of ``instances`` keep the bind window open (Decision 19,
    R3 - charm only). Shared by ``bind_window_open`` and the ``release_closed_bind_windows``
    sweep so there is one rule."""
    return any(
        i.condition.sets_allegiance == Allegiance.ALLY_OF_CASTER
        and i.source_character_id is not None
        and i.source_character.db_location_id == opponent.objectdb.db_location_id
        for i in instances
    )


def bind_window_open(opponent: CombatOpponent) -> bool:
    """Decision 19: a charmed nameless enemy stays bindable while its charmer is here."""
    from world.npc_services.allegiance import allegiance_instances_for  # noqa: PLC0415

    if (
        opponent.status != OpponentStatus.WON_OVER
        or not opponent.objectdb_is_ephemeral
        or opponent.objectdb_id is None
    ):
        return False
    instances = allegiance_instances_for([opponent.objectdb_id]).get(opponent.objectdb_id, [])
    return _window_open(opponent, instances)


def delete_won_over_npc(opponent: CombatOpponent) -> bool:
    """Guarded delete of one won-over ephemeral NPC past its bind window
    (Decision 19).

    Delegates to the shared ``delete_ephemeral_npc`` guard
    (``world/combat/services.py``) — the same Layer-5 checks and
    identity-map-safe delete ``cleanup_completed_encounter``'s generic
    ephemeral sweep uses (#4091 fix round 2: one guard, one fix, not two
    copies of either).
    """
    from world.combat.services import delete_ephemeral_npc  # noqa: PLC0415

    return delete_ephemeral_npc(opponent)


def release_closed_bind_windows() -> int:
    """Delete every WON_OVER ephemeral NPC whose bind window has closed (Decision 19).

    Batched: one query for the candidates, one ``allegiance_instances_for`` call covering
    every candidate's objectdb at once. Returns the number deleted.
    """
    from world.npc_services.allegiance import allegiance_instances_for  # noqa: PLC0415

    candidates = list(
        CombatOpponent.objects.filter(
            status=OpponentStatus.WON_OVER,
            objectdb_is_ephemeral=True,
            objectdb__isnull=False,
        ).select_related("objectdb")
    )
    if not candidates:
        return 0
    by_target = allegiance_instances_for(o.objectdb_id for o in candidates)
    count = 0
    for opponent in candidates:
        instances = by_target.get(opponent.objectdb_id, [])
        if not _window_open(opponent, instances) and delete_won_over_npc(opponent):
            count += 1
    return count


def release_won_over_npcs_in_room(room: ObjectDB) -> int:
    """Delete every WON_OVER ephemeral NPC currently located in ``room`` (scene finish).

    Called at scene teardown so a still-open charmed-nameless bind window doesn't
    outlive the scene (Decision 19, R3). Returns the number deleted.
    """
    candidates = CombatOpponent.objects.filter(
        status=OpponentStatus.WON_OVER,
        objectdb_is_ephemeral=True,
        objectdb__db_location=room,
    ).select_related("objectdb")
    count = 0
    for opponent in candidates:
        if delete_won_over_npc(opponent):
            count += 1
    return count


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


def won_over_snapshot(encounter: CombatEncounter) -> WonOverSnapshot:
    """The viewer-independent half of the digest rows, read while the bodies exist.

    ``complete_encounter`` takes this BEFORE ``cleanup_completed_encounter``
    (#4091 final review): cleanup deletes ephemeral WON_OVER bodies and their
    allegiance instances cascade away with them. ``applied_since=encounter.created_at``
    (ruling R1), same as ``won_over_labels``. Batched: one opponent query, one
    instance query, one persona-name query pair.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
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
    instances: dict[int, list[ConditionInstance]] = {}
    designations: dict[int, ConditionInstance] = {}
    for opponent in opponents:
        mine = by_target.get(opponent.objectdb_id, []) if opponent.objectdb_id else []
        instances[opponent.pk] = mine
        instance = designating_instance(mine)
        if instance is not None:
            designations[opponent.pk] = instance

    source_ids = {
        instance.source_character_id
        for instance in designations.values()
        if instance.source_character_id is not None
    }
    source_names = persona_names_for_sheets(source_ids)
    source_labels = {
        pk: _source_label(instance, source_names) for pk, instance in designations.items()
    }
    return WonOverSnapshot(
        opponents=[o for o in opponents if o.pk in designations],
        instances=instances,
        designations=designations,
        source_labels=source_labels,
    )


def refresh_won_over_holds(
    encounter: CombatEncounter, snapshot: WonOverSnapshot
) -> WonOverSnapshot:
    """The snapshot with each SURVIVING body's holds re-read as they stand now.

    Called by ``complete_encounter`` after cleanup, once for every viewer (one
    batched query). Cleanup's ``expire_end_of_combat_conditions`` may have removed
    an UNTIL_END_OF_COMBAT hold from a persistent NPC since the snapshot; a row built
    from the stale instance would show a badge and offer actions the server then
    refuses. Name, verb and source label stay from the snapshot; a body cleanup
    deleted keeps its pre-cleanup instances (its row is inert either way).
    """
    from world.npc_services.allegiance import allegiance_instances_for  # noqa: PLC0415

    survivors = [o for o in snapshot.opponents if o.objectdb_id is not None]
    by_target = allegiance_instances_for(
        (o.objectdb_id for o in survivors), applied_since=encounter.created_at
    )
    instances = dict(snapshot.instances)
    for opponent in survivors:
        instances[opponent.pk] = by_target.get(opponent.objectdb_id, [])
    return replace(snapshot, instances=instances)


def won_over_rows(
    encounter: CombatEncounter,
    viewer: CharacterSheet,
    *,
    snapshot: WonOverSnapshot | None = None,
) -> list[WonOverRow]:
    """One row per WON_OVER opponent of the encounter, for the digest (#4091).

    Every WON_OVER opponent is included (not only this viewer's own charms) —
    the action flags are what differ per viewer. Pass the ``snapshot`` taken
    before cleanup (``complete_encounter`` does) so a body cleanup deleted still
    gets its row; without one, a fresh snapshot is read now. A deleted body reads
    ``present=False`` with every action flag False and no condition badge (its
    instance no longer exists).

    The badge and the action flags come from ``snapshot.instances``, which
    ``refresh_won_over_holds`` re-reads for surviving bodies after cleanup (see
    there). A surviving body whose hold is gone keeps its row, with no badge and
    no actions.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        ALLEGIANCE_HOLD_KINDS,
        actor_holds_sway_present,
        designating_instance,
        won_over_verb,
    )

    if snapshot is None:
        snapshot = won_over_snapshot(encounter)

    viewer_char = viewer.character
    viewer_char_id = viewer.character_id
    charm_kinds = frozenset({Allegiance.ALLY_OF_CASTER})
    rows: list[WonOverRow] = []
    for opponent in snapshot.opponents:
        instance = snapshot.designations[opponent.pk]
        instances = snapshot.instances.get(opponent.pk, [])
        live = designating_instance(instances)
        # No live hold (body deleted, or the hold ended in cleanup): nothing to act on.
        body = opponent.objectdb if opponent.objectdb_id is not None and live else None

        persona_id = opponent.persona_id
        present = opponent.objectdb_id is not None and opponent.objectdb.location is not None
        current = live or instance
        is_source = current.source_character_id == viewer_char_id
        charmer_is_viewer = (
            is_source and current.condition.sets_allegiance == Allegiance.ALLY_OF_CASTER
        )
        visible_condition = (
            current
            if body is not None and (current.condition.is_visible_to_others or is_source)
            else None
        )

        rows.append(
            WonOverRow(
                opponent_id=opponent.pk,
                name=opponent.name,
                verb=won_over_verb(instance.condition.sets_allegiance),
                source_label=snapshot.source_labels[opponent.pk],
                nameless=opponent.objectdb_is_ephemeral,
                persona_id=persona_id,
                present=present,
                condition=visible_condition,
                holds_until_settled=current.condition.default_duration_type == DurationType.ROUNDS,
                strength=current.effective_severity,
                # Decision 19: the same bind-window predicate telnet's `companion
                # promote` and `promote_summon_to_companion` consult (#4091 fix
                # round 1) — a charm alone is not enough; the charmer must still
                # be in the room. Reuses the snapshot's instances to stay batched.
                can_bind=body is not None
                and charmer_is_viewer
                and _window_open(opponent, instances),
                # The ONE shared presence+hold predicate (``actor_holds_sway_present``)
                # also used by the persona menu, telnet and the action prerequisites
                # (#4091 task 12; take-into-service gated the same way in the final
                # review: the button showed while the action refused).
                can_take_into_service=(
                    body is not None
                    and persona_id is not None
                    and charmer_is_viewer
                    and actor_holds_sway_present(
                        viewer_char, body, kinds=charm_kinds, instances=instances
                    )
                ),
                can_send_away=(
                    body is not None
                    and actor_holds_sway_present(
                        viewer_char, body, kinds=ALLEGIANCE_HOLD_KINDS, instances=instances
                    )
                ),
                can_settle=body is not None and persona_id is not None and present,
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
