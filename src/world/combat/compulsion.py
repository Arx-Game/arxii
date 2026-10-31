"""A compulsion in combat (#4802; Berserk's teeth since #2845).

A character who carries a condition with a ``Compulsion`` (Berserk, a curse at its last
stage) is driven toward what it wants: today, attacking an opponent. Nothing is refused.
These seams make the drive real, for every compulsion staff author:

- **At the round lock** (`resolve_compulsions`): a compelled player character whose
  declared action is not an attack on an opponent rolls the compulsion's resist check.
  The difficulty is the compulsion's base, plus its per-severity step times the
  condition's severity, plus the extra difficulty of a forbidden action (flee, parley).
  The outcome's band says what happens: the action goes ahead freely, goes ahead at a
  penalty on its own roll, or the compulsion acts and the declaration is replaced by the
  compulsion attack. An ally may steady a failed roll for a second one (``try_steady``).
  NPCs never roll.
- **Idle** (`select_compelled_actions`): a compelled participant with no declared action
  gets their simplest damaging technique auto-declared against the first active
  opponent, at the same DECLARING to RESOLVING boundary as the NPC auto-selection
  fallback. Every opponent in an encounter already passed the gates to be there (risk
  acknowledgement, hostile-cast entry), so targeting them raises no new consent question.
- **Walking away** (`reject_leave_if_compelled`): leaving the encounter is still refused
  until leaving rolls like any other forbidden action (#4802 Task 6).
- **Out of combat** (`berserk_rampage_window`): at each reconcile window a compelled
  character auto-engages the nearest NPC in the room through the same hostile-cast
  seeding a deliberate attack uses; with nobody to grab, they rage harmlessly. PC targets
  are NOT grabbed outside combat in v1; a PC becomes a valid rampage target only by
  entering the fight.

The compulsion attack is deliberately modest (lowest-level pure-damage technique, medium
effort, no combos), so round pacing keeps the pre-kill grace window real: nothing dies
to the first swing, and bystanders get rounds to talk the beast down.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import CombatManeuver
from world.combat.types import CompulsionCost, CompulsionRoll
from world.conditions.constants import CompulsionForbidden, CompulsionResult
from world.conditions.control_loss import active_compulsion, has_compulsion

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.combat.models import (
        CombatEncounter,
        CombatOpponent,
        CombatParticipant,
        CombatRoundAction,
    )
    from world.conditions.models import (
        Compulsion,
        CompulsionForbiddenAction,
        CompulsionResistBand,
        ConditionInstance,
    )
    from world.magic.models import Technique
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

RAMPAGE_EMIT = (
    "{name} rages at nothing and everything, claws raking the air, hunting for something to break."
)
BERSERK_LEAVE_REFUSAL = "The rage will not walk away. You can still try to flee."

#: Maneuvers that are attacks, so a compelled character makes them with no roll (R10).
_ATTACK_MANEUVERS = frozenset(
    {CombatManeuver.CHARGE, CombatManeuver.JOUST, CombatManeuver.AWAIT_OPENING}
)

#: The declared maneuvers a compulsion can name as forbidden, by maneuver.
_FORBIDDEN_BY_MANEUVER: dict[str, str] = {
    CombatManeuver.FLEE: CompulsionForbidden.FLEE,
    CombatManeuver.PARLEY: CompulsionForbidden.PARLEY,
}


def reject_leave_if_compelled(participant: CombatParticipant) -> None:
    """Raise ValueError when a compelled participant tries to leave the encounter.

    Called by ``leave_encounter`` only. Flee and parley are not refused: they roll
    against the compulsion at the round lock.
    """
    character = participant.character_sheet.character
    if character is not None and has_compulsion(character):
        raise ValueError(BERSERK_LEAVE_REFUSAL)


# -- the resist roll ---------------------------------------------------------------


def compulsion_difficulty(
    compulsion: Compulsion,
    instance: ConditionInstance,
    forbidden: str | None,
    *,
    forbidden_row: CompulsionForbiddenAction | None = None,
) -> int:
    """The resist roll's difficulty: base, plus per severity, plus a forbidden extra.

    ``forbidden`` is a ``CompulsionForbidden`` value; it adds that action's
    ``extra_difficulty`` only when the compulsion names it. A caller that already
    fetched the row passes it as ``forbidden_row`` and no query is made.
    """
    if forbidden_row is None and forbidden is not None:
        forbidden_row = _forbidden_row(compulsion, forbidden)
    extra = forbidden_row.extra_difficulty if forbidden_row is not None else 0
    return (
        compulsion.base_difficulty + compulsion.difficulty_per_severity * instance.severity + extra
    )


def _forbidden_row(compulsion: Compulsion, forbidden: str) -> CompulsionForbiddenAction | None:
    """The compulsion's row naming *forbidden*, or None when it does not forbid it."""
    return compulsion.forbidden.filter(action=forbidden).order_by("pk").first()


def compulsion_band(
    compulsion: Compulsion,
    outcome: CheckOutcome | None,
) -> CompulsionResistBand | None:
    """The compulsion's band for a roll outcome, or None when staff authored none."""
    if outcome is None:
        return None
    return compulsion.bands.filter(outcome_id=outcome.pk).order_by("pk").first()


def _is_compelled_attack(action: CombatRoundAction) -> bool:
    """Whether the declaration is what the compulsion wants: an attack on an opponent.

    A technique at an opponent with no maneuver, or an attack maneuver with its strike
    technique: a charge, a joust, a waiting strike (a joust and a waiting strike name no
    opponent until they land).
    """
    if action.focused_action_id is None:
        return False
    if action.maneuver:
        return action.maneuver in _ATTACK_MANEUVERS
    return action.focused_opponent_target_id is not None


def _forbidden_key(action: CombatRoundAction) -> str | None:
    """The ``CompulsionForbidden`` value a declared maneuver maps to, if any."""
    if not action.maneuver:
        return None
    return _FORBIDDEN_BY_MANEUVER.get(action.maneuver)


def _cost(
    compulsion: Compulsion,
    instance: ConditionInstance,
    action: CombatRoundAction,
) -> CompulsionCost | None:
    """What *action* costs under this compulsion; None when it is what the compulsion wants."""
    if _is_compelled_attack(action):
        return None
    key = _forbidden_key(action)
    row = _forbidden_row(compulsion, key) if key is not None else None
    return CompulsionCost(
        difficulty=compulsion_difficulty(compulsion, instance, key, forbidden_row=row),
        forbidden=row is not None,
    )


def compulsion_against(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> CompulsionCost | None:
    """What declaring *action* costs *participant* this round, or None when it costs nothing.

    None when the participant carries no compulsion, or when the action is what the
    compulsion wants (a technique at an opponent, with no maneuver).
    """
    character = participant.character_sheet.character
    if character is None:
        return None
    found = active_compulsion(character)
    if found is None:
        return None
    compulsion, instance = found
    return _cost(compulsion, instance, action)


def resolve_compulsions(encounter: CombatEncounter) -> list[CompulsionRoll]:
    """Roll the resist check for every compelled player character acting against it.

    Runs at the DECLARING to RESOLVING boundary, before ``select_compelled_actions``.
    A participant with no declaration, an NPC (NPCs never roll), or a declaration the
    compulsion wants rolls nothing. Never raises for a failed replacement: with nothing to
    attack, the declaration is cancelled and the round says so.
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatRoundAction  # noqa: PLC0415
    from world.roster.services.activity import is_player_character  # noqa: PLC0415

    actions = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        participant__status=ParticipantStatus.ACTIVE,
        round_number=encounter.round_number,
    ).select_related(
        "participant",
        "participant__character_sheet",
        "focused_action",
        "focused_opponent_target",
    )
    rolls: list[CompulsionRoll] = []
    for action in actions.order_by("participant_id"):
        participant = action.participant
        character = participant.character_sheet.character
        if character is None:
            continue
        found = active_compulsion(character)
        if found is None or not is_player_character(participant.character_sheet):
            continue
        compulsion, instance = found
        cost = _cost(compulsion, instance, action)
        if cost is None:
            continue
        rolls.append(_resist(participant, action, compulsion, cost.difficulty))
    return rolls


def _resist(
    participant: CombatParticipant,
    action: CombatRoundAction,
    compulsion: Compulsion,
    difficulty: int,
) -> CompulsionRoll:
    """One resist roll, its steadying pass, and its band applied."""
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.combat.services.reactions import try_steady  # noqa: PLC0415

    character = participant.character_sheet.character
    first = perform_check_with_modifiers(
        character, compulsion.check_type, target_difficulty=difficulty
    )
    name = _name(participant)
    _tell_room(
        participant,
        f"{name} tries to {_action_label(action)} against "
        f"{compulsion.condition.name}. {compulsion.check_type.name} vs {difficulty}: "
        f"{_outcome_name(first)}.",
    )
    band = compulsion_band(compulsion, first.outcome)
    if band is not None and band.result == CompulsionResult.COMPULSION_ACTS:
        second = try_steady(participant, compulsion, difficulty)
        if second is not None:
            band = compulsion_band(compulsion, second.outcome)
    _apply_band(participant, action, compulsion, band, name=name)
    return CompulsionRoll(
        participant=participant,
        action=action,
        difficulty=difficulty,
        first_result=first,
        steadied_by=None,
        final_band=band,
    )


def _apply_band(
    participant: CombatParticipant,
    action: CombatRoundAction,
    compulsion: Compulsion,
    band: CompulsionResistBand | None,
    *,
    name: str,
) -> None:
    """Strain the action, or replace it with the compulsion attack, and move control.

    ``name`` is the participant's persona name, for the round line.
    """
    if band is None:
        return
    if band.result == CompulsionResult.ACTS_STRAINED:
        action.compulsion_penalty = band.action_penalty
        action.save(update_fields=["compulsion_penalty"])
    elif band.result == CompulsionResult.COMPULSION_ACTS:
        _compulsion_acts(participant, action, compulsion, name=name)
    if band.control_change:
        _shift_control(participant, band.control_change)


def _compulsion_acts(
    participant: CombatParticipant,
    action: CombatRoundAction,
    compulsion: Compulsion,
    *,
    name: str,
) -> None:
    """Delete the declaration and declare the compulsion attack in its place.

    With no damaging technique, no active opponent, or a compulsion attack that fails to
    declare, the declaration is only cancelled; the round says so and nothing is raised.
    """
    label = _action_label(action)
    action.delete()
    target = _first_active_opponent(participant)
    technique = compulsion_technique_for(participant.character_sheet)
    replaced = None
    if target is not None and technique is not None:
        replaced = _declare_rage_attack(participant, technique, target)
    condition = compulsion.condition.name
    if replaced is not None and target is not None:
        _tell_room(participant, f"{condition} wins out: {name} attacks {target.name}.")
    else:
        _tell_room(participant, f"{condition} wins out: {name} gives up trying to {label}.")


def _shift_control(participant: CombatParticipant, control_change: int) -> None:
    """Land a band's control change on the participant's engagement, if one exists."""
    from world.magic.services.fury import engagement_of, shift_engagement  # noqa: PLC0415

    engagement = engagement_of(participant.character_sheet.character)
    if engagement is None:
        return
    shift_engagement(engagement, intensity=0, control=control_change, surrendered=0)


def _action_label(action: CombatRoundAction) -> str:
    """The declaration as a verb phrase for the round line: "flee", "use Mend"."""
    if action.maneuver:
        return CombatManeuver(action.maneuver).label.lower()
    if action.focused_action is not None:
        return f"use {action.focused_action.name}"
    return "hold back"


def _outcome_name(result: CheckResult) -> str:
    return result.outcome.name if result.outcome is not None else "no result"


def _name(participant: CombatParticipant) -> str:
    """The persona name others know the participant by."""
    from world.combat.surge_rolls import persona_name_of  # noqa: PLC0415

    return persona_name_of(participant)


def _tell_room(participant: CombatParticipant, line: str) -> None:
    """Send a round line to the fight's room once the round commits.

    The room includes the character; with no room, only the character is told.
    """
    room = participant.encounter.room
    character = participant.character_sheet.character
    if room is not None:
        transaction.on_commit(lambda: room.msg_contents(line))
    elif character is not None:
        transaction.on_commit(lambda: character.msg(line))


def _first_active_opponent(participant: CombatParticipant) -> CombatOpponent | None:
    """The first active opponent in the participant's encounter, never the character."""
    from world.combat.constants import OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    return (
        CombatOpponent.objects.filter(
            encounter_id=participant.encounter_id,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(objectdb=participant.character_sheet.character)
        .order_by("pk")
        .first()
    )


# -- the compulsion attack ---------------------------------------------------------


def compulsion_technique_for(sheet: CharacterSheet) -> Technique | None:
    """The technique the rage swings with: the simplest damaging one known.

    Lowest-level pure-damage pick (basic-attack-only compulsion, ruled); granted
    battle-form techniques qualify like any other known technique.
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


def select_compelled_actions(encounter: CombatEncounter) -> list[CombatRoundAction]:
    """Auto-declare attacks for compelled participants with no declared action.

    Idempotent within a round (skips participants who already declared; steering their
    own rage counts). A participant whose declaration fails validation (no anima, no
    target, incapacitated) simply doesn't act this round; the failure is logged, never
    raised, so the sweep cannot abort round resolution.
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant, CombatRoundAction  # noqa: PLC0415

    declared: list[CombatRoundAction] = []
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet")
    for participant in participants:
        character = participant.character_sheet.character
        if character is None or not has_compulsion(character):
            continue
        already = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).exists()
        if already:
            continue
        target = _first_active_opponent(participant)
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
    """One compelled declaration; validation failures skip, never abort.

    Never consents to Soulfray risk on the player's behalf (AFK never kills): a strike
    that would need Soulfray lapses at resolution like any unconsented cast.
    """
    from world.combat.services import declare_action  # noqa: PLC0415
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415

    try:
        return declare_action(
            participant,
            focused_action=technique,
            focused_category=technique.action_category,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=target,
            confirm_soulfray_risk=False,
        )
    except ValueError as exc:
        logger.info(
            "Compulsion could not declare for participant pk=%s: %s",
            participant.pk,
            exc,
        )
        return None


# -- out of combat -----------------------------------------------------------------


def berserk_rampage_window(character: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM - the cron holds characters
    """One out-of-combat rampage window for a compelled character (#2845).

    Auto-engages the nearest NPC in the room through the hostile-cast seeding seam (the
    same entry a deliberate attack uses, so evidence, stakes, and risk plumbing all ride
    along). With no NPC present, the rage vents harmlessly; bystander PCs are never
    grabbed outside combat in v1.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if not has_compulsion(character):
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
        room.msg_contents(RAMPAGE_EMIT.format(name=_persona_name(character)))
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
        room.msg_contents(RAMPAGE_EMIT.format(name=_persona_name(sheet.character)))


def _persona_name(character: ObjectDB) -> str:  # noqa: OBJECTDB_PARAM - the rampage holds characters
    """The persona name others know *character* by; the key when there is no sheet."""
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return character.key
    return persona_names_for_sheets([sheet.pk]).get(sheet.pk, character.key)


def _nearest_npc_sheet(character: ObjectDB, room: ObjectDB) -> CharacterSheet | None:
    """The first living sheeted NPC co-located with the berserker.

    A berserk rampage must never target a PC (PCs roll, NPCs are targets). The canonical,
    offline-safe PC test is ``is_player_character`` (an active RosterTenure or a live
    puppet), not ``db_account`` alone (#4091): an offline PC's ``db_account`` reads
    ``None``, which would have let a rampage target them. A story NPC a GM or Guide plays
    is still a valid target (#4418, ADR-4418).
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.roster.services.activity import is_player_character  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    for obj in room.contents:
        if obj == character:
            continue
        try:
            sheet = obj.character_sheet
        except (AttributeError, ObjectDoesNotExist):
            continue
        if sheet is None or is_player_character(sheet):
            continue
        if can_act(sheet):
            return sheet
    return None


def _in_uncompleted_encounter(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Whether the character already participates in an uncompleted encounter."""
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return False
    return CombatParticipant.objects.filter(
        character_sheet=sheet,
        encounter__completed_at__isnull=True,
    ).exists()
