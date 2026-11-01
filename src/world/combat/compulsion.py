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
- **Walking away and changing back** (`resist_compulsion_now`): leaving an encounter and
  reverting an alternate self roll the same check, at once, with no declaration to replace
  and no ally to steady it (there is no round to spend a reaction in). A failed roll
  cannot be retried at once: in combat the next try is next round, out of combat it
  waits ``Compulsion.retry_wait_minutes``.
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
import math
from typing import TYPE_CHECKING

from world.combat.constants import CombatManeuver
from world.combat.types import CompulsionAttempt, CompulsionCost, CompulsionRoll
from world.conditions.constants import CompulsionForbidden, CompulsionResult
from world.conditions.control_loss import (
    active_compulsion,
    active_compulsions_for,
    compulsion_difficulty,
    compulsion_summary_for,
    display_name_of,
    forbidden_rows_for,
)
from world.conditions.types import CompulsionOption, CompulsionSummary

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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

#: Maneuvers that are attacks, so a compelled character makes them with no roll (R10).
_ATTACK_MANEUVERS = frozenset(
    {CombatManeuver.CHARGE, CombatManeuver.JOUST, CombatManeuver.AWAIT_OPENING}
)

#: The declared maneuvers a compulsion can name as forbidden, by maneuver.
_FORBIDDEN_BY_MANEUVER: dict[str, str] = {
    CombatManeuver.FLEE: CompulsionForbidden.FLEE,
    CombatManeuver.PARLEY: CompulsionForbidden.PARLEY,
}


# -- the resist roll ---------------------------------------------------------------


def compulsion_band(
    compulsion: Compulsion,
    outcome: CheckOutcome | None,
    bands: Mapping[int, CompulsionResistBand] | None = None,
) -> CompulsionResistBand | None:
    """The compulsion's band for a roll outcome, or None when staff authored none.

    A caller that already read the compulsion's bands passes them, keyed by outcome id
    (``bands_by_outcome``), and no query is made.
    """
    if outcome is None:
        return None
    if bands is not None:
        return bands.get(outcome.pk)
    return compulsion.bands.filter(outcome_id=outcome.pk).order_by("pk").first()


def bands_by_outcome(
    compulsions: Sequence[Compulsion],
) -> dict[int, dict[int, CompulsionResistBand]]:
    """Each compulsion's bands by outcome id, keyed by compulsion pk (one query)."""
    from world.conditions.models import CompulsionResistBand  # noqa: PLC0415

    bands: dict[int, dict[int, CompulsionResistBand]] = {c.pk: {} for c in compulsions}
    for band in CompulsionResistBand.objects.filter(compulsion_id__in=list(bands)).order_by("pk"):
        bands[band.compulsion_id].setdefault(band.outcome_id, band)
    return bands


#: The verb phrase the roll line uses for each action resolved outside the round.
_OUTSIDE_ROUND_LABEL: dict[str, str] = {
    CompulsionForbidden.LEAVE: "leave the encounter",
    CompulsionForbidden.REVERT_FORM: "change back",
}


def resist_compulsion_now(character: ObjectDB, forbidden: str) -> CompulsionAttempt:  # noqa: OBJECTDB_PARAM
    """Roll the resist check for *character* leaving an encounter or changing back.

    ``forbidden`` is ``CompulsionForbidden.LEAVE`` or ``REVERT_FORM``. A character with no
    compulsion (Charmed, Calm) and any NPC (NPCs never roll) go ahead with nothing rolled.
    The difficulty and the band come from the same helpers the round lock uses; there is
    no steadying here. The band's ``control_change`` lands whatever the result.

    A failed roll cannot be retried at once (ruled 2026-10-31): a fighter in an
    uncompleted encounter tries again next round (``compulsion_attempt_round``); anyone
    else waits the compulsion's ``retry_wait_minutes`` (``compulsion_retry_after`` on the
    condition instance). A try inside that window rolls nothing and comes back with
    ``waiting`` set and a line saying when to try again.

    ACTS_STRAINED lets the action happen: leaving and changing back have no roll of
    their own, so the band's action penalty has nothing to reduce.

    The room hears the line; the character hears it themself on success, and on failure
    from the caller's refusal message, so it is never told twice.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.roster.services.activity import is_player_character  # noqa: PLC0415

    found = active_compulsion(character)
    sheet = character.character_sheet
    if found is None or sheet is None or not is_player_character(sheet):
        return CompulsionAttempt(allowed=True, line="", check_result=None)
    compulsion, instance = found
    seat = _fighting_seat(sheet)
    wait = _retry_wait_line(compulsion, instance, seat)
    if wait is not None:
        return CompulsionAttempt(allowed=False, line=wait, check_result=None, waiting=True)
    difficulty = compulsion_difficulty(compulsion, instance, forbidden)
    result = perform_check_with_modifiers(
        character, compulsion.check_type, target_difficulty=difficulty
    )
    line = (
        f"{display_name_of(character)} tries to {_OUTSIDE_ROUND_LABEL[forbidden]} against "
        f"{compulsion.condition.name}. {compulsion.check_type.name} vs {difficulty}: "
        f"{_outcome_name(result)}."
    )
    band = compulsion_band(compulsion, result.outcome)
    allowed = band is None or band.result != CompulsionResult.COMPULSION_ACTS
    if band is not None and band.control_change:
        _shift_character_control(character, band.control_change)
    if not allowed:
        _start_retry_wait(compulsion, instance, seat)
    if character.location is not None:
        character.location.msg_contents(line, exclude=[character])
    if allowed:
        character.msg(line)
    return CompulsionAttempt(allowed=allowed, line=line, check_result=result)


def _fighting_seat(sheet: CharacterSheet) -> CombatParticipant | None:
    """The sheet's active seat in an uncompleted encounter, if they are in a fight."""
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    return (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__completed_at__isnull=True,
        )
        .select_related("encounter")
        .order_by("pk")
        .first()
    )


def _retry_wait_line(
    compulsion: Compulsion,
    instance: ConditionInstance,
    seat: CombatParticipant | None,
) -> str | None:
    """The line refusing a retry inside the wait after a failed roll, or None to roll."""
    from django.utils import timezone  # noqa: PLC0415

    name = compulsion.condition.name
    if seat is not None:
        if seat.compulsion_attempt_round == seat.encounter.round_number:
            return f"{name} still holds you. You can try again next round."
        return None
    retry_after = instance.compulsion_retry_after
    now = timezone.now()
    if retry_after is None or retry_after <= now:
        return None
    minutes = max(1, math.ceil((retry_after - now).total_seconds() / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"{name} still holds you. You can try again in {minutes} {unit}."


def _start_retry_wait(
    compulsion: Compulsion,
    instance: ConditionInstance,
    seat: CombatParticipant | None,
) -> None:
    """Record a failed roll so the next try waits: the round in a fight, minutes outside."""
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    if seat is not None:
        seat.compulsion_attempt_round = seat.encounter.round_number
        seat.save(update_fields=["compulsion_attempt_round"])
        return
    instance.compulsion_retry_after = timezone.now() + timedelta(
        minutes=compulsion.retry_wait_minutes
    )
    instance.save(update_fields=["compulsion_retry_after"])


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
    forbidden: Mapping[str, CompulsionForbiddenAction],
) -> CompulsionCost | None:
    """What *action* costs under this compulsion; None when it is what the compulsion wants.

    ``forbidden`` is the compulsion's forbidden rows by action (``forbidden_rows_for``).
    """
    if _is_compelled_attack(action):
        return None
    key = _forbidden_key(action)
    row = forbidden.get(key) if key is not None else None
    return CompulsionCost(
        difficulty=compulsion_difficulty(compulsion, instance, key, row=row),
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
    return _cost(compulsion, instance, action, forbidden_rows_for([compulsion])[compulsion.pk])


#: The panel key for a technique that names no opponent (a defend, a heal).
NO_TARGET_TECHNIQUE_KEY = "technique_no_target"

#: The maneuvers that write a round action and so are charged by ``resolve_compulsions``
#: when they are not attacks. Engage, disengage and yield declare no round action.
_ROUND_MANEUVERS = (
    CombatManeuver.FLEE,
    CombatManeuver.COVER,
    CombatManeuver.INTERPOSE,
    CombatManeuver.SUCCOR,
    CombatManeuver.RALLY,
    CombatManeuver.DEMORALIZE,
    CombatManeuver.TAUNT,
    CombatManeuver.PARLEY,
    CombatManeuver.USE_ITEM,
)

#: Actions resolved outside the round, each rolled at once by ``resist_compulsion_now``.
_OUTSIDE_ROUND = (CompulsionForbidden.LEAVE, CompulsionForbidden.REVERT_FORM)


def _summary_options() -> list[CompulsionOption]:
    """The actions the declare panel costs: round maneuvers, a no-target technique, and the
    two actions resolved outside the round. Labels are the existing display labels."""
    return [
        *(
            CompulsionOption(str(m), str(m.label), _FORBIDDEN_BY_MANEUVER.get(m))
            for m in _ROUND_MANEUVERS
        ),
        CompulsionOption(NO_TARGET_TECHNIQUE_KEY, None, None),
        *(CompulsionOption(str(o), str(o.label), str(o)) for o in _OUTSIDE_ROUND),
    ]


def compulsion_summary(
    participant: CombatParticipant,
    active_instances: Sequence[ConditionInstance] | None = None,
) -> CompulsionSummary | None:
    """The participant's compulsion and every declarable action's cost, for the declare panel.

    Also names who the rage would strike as things stand (the first active opponent, when
    there is a technique to swing), looked up once for the viewer, not once per option.
    """
    character = participant.character_sheet.character
    if character is None:
        return None
    found = active_compulsion(character, active_instances)
    if found is None:
        return None
    opponent = _first_active_opponent(participant)
    technique = compulsion_technique_for(participant.character_sheet)
    target = opponent.name if opponent is not None and technique is not None else None
    return compulsion_summary_for(
        character, _summary_options(), found=found, attack_target_name=target
    )


def compulsion_warning(participant: CombatParticipant, action: CombatRoundAction) -> str | None:
    """The line a telnet declare prints when *action* goes against the compulsion."""
    character = participant.character_sheet.character
    found = active_compulsion(character) if character is not None else None
    if found is None:
        return None
    compulsion, instance = found
    cost = _cost(compulsion, instance, action, forbidden_rows_for([compulsion])[compulsion.pk])
    if cost is None:
        return None
    return (
        f"Against {compulsion.condition.name}: {compulsion.check_type.name} check, "
        f"difficulty {cost.difficulty}. If it fails, you attack instead."
    )


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
    actions = list(actions.order_by("participant_id"))
    characters = [
        a.participant.character_sheet.character
        for a in actions
        if a.participant.character_sheet.character is not None
    ]
    # Every compulsion row this round needs is read once, not once per action.
    found_by_character = active_compulsions_for(characters)
    compulsions = list({c.pk: c for c, _ in found_by_character.values()}.values())
    forbidden = forbidden_rows_for(compulsions)
    bands = bands_by_outcome(compulsions)
    rolls: list[CompulsionRoll] = []
    for action in actions:
        participant = action.participant
        character = participant.character_sheet.character
        found = found_by_character.get(character.pk) if character is not None else None
        if found is None or not is_player_character(participant.character_sheet):
            continue
        compulsion, instance = found
        cost = _cost(compulsion, instance, action, forbidden[compulsion.pk])
        if cost is None:
            continue
        rolls.append(
            _resist(participant, action, compulsion, cost.difficulty, bands[compulsion.pk])
        )
    return rolls


def _resist(
    participant: CombatParticipant,
    action: CombatRoundAction,
    compulsion: Compulsion,
    difficulty: int,
    bands: Mapping[int, CompulsionResistBand],
) -> CompulsionRoll:
    """One resist roll, its steadying pass, and its band applied.

    ``bands`` is the compulsion's bands by outcome id (``bands_by_outcome``).
    """
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
    band = compulsion_band(compulsion, first.outcome, bands)
    steadied_by = None
    if band is not None and band.result == CompulsionResult.COMPULSION_ACTS:
        steady = try_steady(participant, compulsion, difficulty)
        if steady is not None:
            steadied_by = steady.steadier
            _tell_room(
                participant,
                f"{_name(steadied_by)} steadies {name}. "
                f"{steady.check_result.check_type.name} vs {difficulty}: "
                f"{_outcome_name(steady.check_result)}.",
            )
            band = compulsion_band(compulsion, steady.check_result.outcome, bands)
    _apply_band(participant, action, compulsion, band, name=name)
    return CompulsionRoll(
        participant=participant,
        action=action,
        difficulty=difficulty,
        first_result=first,
        steadied_by=steadied_by,
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
    _shift_character_control(participant.character_sheet.character, control_change)


def _shift_character_control(character: ObjectDB, control_change: int) -> None:  # noqa: OBJECTDB_PARAM
    """Land a band's control change on *character*'s engagement, if one exists."""
    from world.magic.services.fury import engagement_of, shift_engagement  # noqa: PLC0415

    engagement = engagement_of(character)
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
    """Send a round line through the round's own narration, in the round's order.

    The same delivery the rest of the round's narration uses (an OUTCOME interaction,
    pushed at once to web and telnet), so the roll line, its outcome and the action it
    led to reach the room before the resolution lines that follow them. With no room
    the row is still kept in the scene log and the character is told directly.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    encounter = participant.encounter
    broadcast_action_outcome(encounter=encounter, narration=line, target_personas=[])
    character = participant.character_sheet.character
    if encounter.room is None and character is not None:
        character.msg(line)


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
    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    compelled = active_compulsions_for(
        [p.character_sheet.character for p in participants if p.character_sheet.character]
    )
    for participant in participants:
        character = participant.character_sheet.character
        if character is None or character.pk not in compelled:
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
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=technique.action_category,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=target,
            confirm_soulfray_risk=False,
        )
        action.declared_by_compulsion = True
        action.save(update_fields=["declared_by_compulsion"])
        return action
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

    if active_compulsion(character) is None:
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
        room.msg_contents(RAMPAGE_EMIT.format(name=display_name_of(character)))
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
        room.msg_contents(RAMPAGE_EMIT.format(name=display_name_of(sheet.character)))


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
