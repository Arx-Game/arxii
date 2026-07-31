"""Berserk compulsion (#2845): a berserker genuinely goes uncontrolled.

Before this module, Berserk was a state flag — it derived ``in_control=False``
(blocking form-revert) but nothing made the character act. These seams add the
teeth, for EVERY Berserk producer (fury, the moon, future demonic sources):

- **In combat** (`select_berserk_actions`): each round, a Berserk participant
  with no declared action gets their simplest damaging technique auto-declared
  against the first active opponent — a sibling of the NPC auto-selection
  fallback, invoked at the same DECLARING→RESOLVING boundary. Every opponent in
  an encounter already passed the gates to be there (risk acknowledgement,
  hostile-cast entry), so targeting them raises no new consent question. The
  player may steer the rage by declaring their own attack first; they cannot
  opt out except through the break-out loop (Restore to Sense / stage decay).
- **Retreat/parley refusal** (`reject_if_berserk`): flee, parley, and leaving
  the encounter are refused while raging.
- **Out of combat** (`berserk_rampage_window`): at each reconcile window a
  Berserk character auto-engages the nearest NPC in the room through the same
  hostile-cast seeding a deliberate attack uses; with nobody to grab, they
  rage harmlessly. PC targets are NOT grabbed outside combat in v1 — a PC
  becomes a valid rampage target only by entering the fight.

The compulsion is deliberately modest — lowest-level pure-damage technique,
medium effort, no combos — so round pacing keeps the pre-kill grace window
real: nothing dies to the first swing, and bystanders get rounds to talk the
beast down.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import (
        CombatEncounter,
        CombatOpponent,
        CombatParticipant,
        CombatRoundAction,
    )
    from world.magic.models import Technique
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

BERSERK_CONDITION_NAME = "Berserk"

RAMPAGE_EMIT = (
    "{name} rages at nothing and everything — claws raking the air, hunting for something to break."
)
BERSERK_REFUSAL = "The rage does not retreat."


def is_berserk(character: ObjectDB) -> bool:
    """Whether the character has an active Berserk condition."""
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    return any(
        instance.condition.name == BERSERK_CONDITION_NAME
        for instance in get_active_conditions(character)
    )


def reject_if_berserk(participant: CombatParticipant, verb: str) -> None:
    """Raise ValueError when a Berserk participant tries to disengage.

    Called by ``declare_flee`` / ``declare_parley`` / ``leave_encounter`` —
    the rage neither retreats nor negotiates (#2845).
    """
    character = participant.character_sheet.character
    if character is not None and is_berserk(character):
        msg = f"Cannot {verb}: {BERSERK_REFUSAL.lower()}"
        raise ValueError(msg)


def compulsion_technique_for(sheet: CharacterSheet) -> Technique | None:
    """The technique the rage swings with: the simplest damaging one known.

    Lowest-level pure-damage pick (basic-attack-only compulsion, ruled) —
    granted battle-form techniques qualify like any other known technique.
    """
    from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

    row = (
        CharacterTechnique.objects.filter(
            character=sheet,
            technique__effect_type__base_power__isnull=False,
        )
        .select_related("technique")
        .order_by("technique__level", "technique__pk")
        .first()
    )
    return row.technique if row is not None else None


def select_berserk_actions(encounter: CombatEncounter) -> list[CombatRoundAction]:
    """Auto-declare attacks for Berserk participants with no declared action.

    Idempotent within a round (skips participants who already declared —
    steering their own rage counts). A participant whose declaration fails
    validation (no anima, no target, incapacitated) simply doesn't act this
    round; the failure is logged, never raised — the sweep must not abort
    round resolution.
    """
    from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
    from world.combat.models import (  # noqa: PLC0415
        CombatOpponent,
        CombatParticipant,
        CombatRoundAction,
    )

    declared: list[CombatRoundAction] = []
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet")
    for participant in participants:
        character = participant.character_sheet.character
        if character is None or not is_berserk(character):
            continue
        already = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).exists()
        if already:
            continue
        target = (
            CombatOpponent.objects.filter(
                encounter=encounter,
                status=OpponentStatus.ACTIVE,
            )
            .exclude(objectdb=character)
            .order_by("pk")
            .first()
        )
        technique = compulsion_technique_for(participant.character_sheet)
        if target is None or technique is None:
            continue
        action = _declare_rage_attack(participant, technique, target)
        if action is not None:
            declared.append(action)
    return declared


def _declare_rage_attack(
    participant: CombatParticipant,
    technique: Technique,
    target: CombatOpponent,
) -> CombatRoundAction | None:
    """One compelled declaration; validation failures skip, never abort."""
    from world.combat.services import declare_action  # noqa: PLC0415
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415

    try:
        return declare_action(
            participant,
            focused_action=technique,
            focused_category=technique.action_category,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=target,
            confirm_soulfray_risk=True,
        )
    except ValueError as exc:
        logger.info(
            "Berserk compulsion could not declare for participant pk=%s: %s",
            participant.pk,
            exc,
        )
        return None


def berserk_rampage_window(character: ObjectDB) -> None:
    """One out-of-combat rampage window for a Berserk character (#2845).

    Auto-engages the nearest NPC in the room through the hostile-cast seeding
    seam (the same entry a deliberate attack uses, so evidence, stakes, and
    risk plumbing all ride along). With no NPC present, the rage vents
    harmlessly — bystander PCs are never grabbed outside combat in v1.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if not is_berserk(character):
        return
    if _in_uncompleted_encounter(character):
        return
    room = character.location
    if room is None:
        return
    sheet = character.character_sheet
    technique = compulsion_technique_for(sheet) if sheet is not None else None
    victim_sheet = _nearest_npc_sheet(character, room)
    scene = get_active_scene(room)
    if sheet is None or technique is None or victim_sheet is None or scene is None:
        room.msg_contents(RAMPAGE_EMIT.format(name=character.key))
        return
    _seed_rampage_encounter(sheet, victim_sheet, technique, scene, room)


def _seed_rampage_encounter(
    sheet: CharacterSheet,
    victim_sheet: CharacterSheet,
    technique: Technique,
    scene: Scene,
    room: ObjectDB,
) -> None:
    """Open (or feed) the encounter; seeding failures emit rather than raise."""
    from world.combat.cast_seed import seed_or_feed_encounter_from_cast  # noqa: PLC0415

    try:
        seed_or_feed_encounter_from_cast(
            caster_sheet=sheet,
            target_sheet=victim_sheet,
            technique=technique,
            scene=scene,
            room=room,
        )
    except ValueError as exc:
        logger.info("Berserk rampage could not seed encounter: %s", exc)
        room.msg_contents(RAMPAGE_EMIT.format(name=sheet.character.key))


def _nearest_npc_sheet(character: ObjectDB, room: ObjectDB) -> CharacterSheet | None:
    """The first living sheeted NPC co-located with the berserker."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.vitals.services import can_act  # noqa: PLC0415

    for obj in room.contents:
        if obj == character:
            continue
        try:
            if obj.db_account is not None:
                continue
            sheet = obj.character_sheet
        except (AttributeError, ObjectDoesNotExist):
            continue
        if sheet is not None and can_act(sheet):
            return sheet
    return None


def _in_uncompleted_encounter(character: ObjectDB) -> bool:
    """Whether the character already participates in an uncompleted encounter."""
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return False
    return CombatParticipant.objects.filter(
        character_sheet=sheet,
        encounter__completed_at__isnull=True,
    ).exists()
