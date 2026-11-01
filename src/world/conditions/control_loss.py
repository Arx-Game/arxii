"""The control-loss trigger engine (#4802).

A character who carries a vulnerability condition (Lycan blood, a curse) is subject to the
``ControlLossTrigger`` rows hung on it. Three callers fire them: the moon sweep
(``world.species.moon_sensitivity``), the damage service (a wound crossing a threshold) and
the condition service (a vulnerability entering a stage). Each fired trigger rolls its
check, looks the outcome up in its bands and applies the band: an engagement shift, a
condition (Berserk), a forced battle form. Every number lives on the rows.

``has_compulsion`` and ``active_compulsion`` answer the other half: is the character
currently compelled, and by what.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.constants import ControlLossFiresOn
from world.conditions.types import (
    CompulsionActionCost,
    CompulsionOption,
    CompulsionSummary,
    ControlLossOutcome,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.combat.models import CombatEncounter
    from world.conditions.models import (
        Compulsion,
        CompulsionForbiddenAction,
        ConditionInstance,
        ConditionStage,
        ControlLossBand,
        ControlLossTrigger,
    )


def active_compulsion(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the cron and combat hold characters
    active_instances: Sequence[ConditionInstance] | None = None,
) -> tuple[Compulsion, ConditionInstance] | None:
    """The compulsion currently driving *character*: highest severity, ties by instance pk.

    Reads the condition handler's cached active list, then one query for the compulsion
    rows of those conditions. A caller that already holds the character's active
    instances (the encounter read preloads them) passes them as ``active_instances``.
    """
    if active_instances is None:
        active_instances = character.conditions.active()
    if not active_instances:
        return None
    return _strongest(active_instances, _compulsions_by_condition(active_instances))


def active_compulsions_for(
    characters: Sequence[ObjectDB],
) -> dict[int, tuple[Compulsion, ConditionInstance]]:
    """``active_compulsion`` for many characters, keyed by character pk, in one query.

    Each character's active instances come from its condition handler's cache; the
    compulsion rows of every carried condition are read together. A character with no
    compulsion is left out.
    """
    instances_by_character = {
        character.pk: character.conditions.active() for character in characters
    }
    every = [inst for insts in instances_by_character.values() for inst in insts]
    if not every:
        return {}
    by_condition = _compulsions_by_condition(every)
    found = {}
    for pk, instances in instances_by_character.items():
        best = _strongest(instances, by_condition)
        if best is not None:
            found[pk] = best
    return found


def _compulsions_by_condition(
    instances: Sequence[ConditionInstance],
) -> dict[int, Compulsion]:
    """The compulsion rows of the instances' conditions, keyed by condition id (one query)."""
    from world.conditions.models import Compulsion  # noqa: PLC0415

    return {
        compulsion.condition_id: compulsion
        for compulsion in Compulsion.objects.filter(
            condition_id__in={inst.condition_id for inst in instances}
        ).select_related("condition", "check_type")
    }


def _strongest(
    instances: Sequence[ConditionInstance],
    by_condition: dict[int, Compulsion],
) -> tuple[Compulsion, ConditionInstance] | None:
    """The compelling instance with the highest severity; ties go to the lowest pk."""
    best: tuple[Compulsion, ConditionInstance] | None = None
    for instance in instances:
        compulsion = by_condition.get(instance.condition_id)
        if compulsion is None:
            continue
        if best is None or (instance.severity, -instance.pk) > (best[1].severity, -best[1].pk):
            best = (compulsion, instance)
    return best


def forbidden_rows_for(
    compulsions: Sequence[Compulsion],
) -> dict[int, dict[str, CompulsionForbiddenAction]]:
    """Each compulsion's forbidden rows by action, keyed by compulsion pk (one query)."""
    from world.conditions.models import CompulsionForbiddenAction  # noqa: PLC0415

    rows: dict[int, dict[str, CompulsionForbiddenAction]] = {c.pk: {} for c in compulsions}
    for row in CompulsionForbiddenAction.objects.filter(compulsion_id__in=list(rows)).order_by(
        "pk"
    ):
        rows[row.compulsion_id].setdefault(row.action, row)
    return rows


def forbidden_row(compulsion: Compulsion, forbidden: str) -> CompulsionForbiddenAction | None:
    """The compulsion's row naming *forbidden*, or None when it does not forbid it."""
    return compulsion.forbidden.filter(action=forbidden).order_by("pk").first()


def compulsion_difficulty(
    compulsion: Compulsion,
    instance: ConditionInstance,
    forbidden: str | None,
    *,
    row: CompulsionForbiddenAction | None = None,
) -> int:
    """The resist roll's difficulty: base, plus per severity, plus a forbidden extra.

    ``forbidden`` is a ``CompulsionForbidden`` value; it adds that action's
    ``extra_difficulty`` only when the compulsion names it. A caller that already
    fetched the row passes it as ``row`` and no query is made.
    """
    if row is None and forbidden is not None:
        row = forbidden_row(compulsion, forbidden)
    extra = row.extra_difficulty if row is not None else 0
    return (
        compulsion.base_difficulty + compulsion.difficulty_per_severity * instance.severity + extra
    )


def compulsion_summary_for(
    character: ObjectDB | None,  # noqa: OBJECTDB_PARAM - the forms and combat reads hold characters
    options: Sequence[CompulsionOption],
    active_instances: Sequence[ConditionInstance] | None = None,
    attack_target_name: str | None = None,
    *,
    found: tuple[Compulsion, ConditionInstance] | None = None,
) -> CompulsionSummary | None:
    """The character's compulsion and what each of *options* costs under it.

    The compulsion and its forbidden rows are read once; each option's cost is derived
    from them, so the number of options adds no queries. A caller that already found the
    compulsion (``active_compulsion``) passes it as ``found`` and it is not looked up again.
    """
    if character is None:
        return None
    if found is None:
        found = active_compulsion(character, active_instances)
    if found is None:
        return None
    compulsion, instance = found
    rows = {row.action: row for row in compulsion.forbidden.all()}
    against = []
    for option in options:
        row = rows.get(option.forbidden_key) if option.forbidden_key is not None else None
        against.append(
            CompulsionActionCost(
                action_key=option.action_key,
                label=option.label,
                difficulty=compulsion_difficulty(compulsion, instance, None, row=row),
                forbidden=row is not None,
                extra_difficulty=row.extra_difficulty if row is not None else 0,
            )
        )
    return CompulsionSummary(
        condition_name=compulsion.condition.name,
        wants_label=compulsion.get_wants_display(),
        check_name=compulsion.check_type.name,
        attack_target_name=attack_target_name,
        against=against,
    )


def has_compulsion(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Whether *character* is currently compelled by any condition."""
    return active_compulsion(character) is not None


def fire_control_loss_triggers(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the moon sweep and damage hold characters
    fires_on: str,
    *,
    moon_pull: int = 0,
    stage: ConditionStage | None = None,
) -> list[ControlLossOutcome]:
    """Fire every trigger of *fires_on* hung on a condition *character* carries.

    ``moon_pull`` gates a moon trigger (its ``min_moon_pull``); ``stage`` selects the
    CONDITION_STAGE triggers for that stage. A trigger that is exempt for the character's
    level rolls nothing and is left out of the result.
    """
    from world.conditions.models import ControlLossTrigger  # noqa: PLC0415

    sheet = _roller_sheet(character)
    if sheet is None:
        return []
    carried = _carried_vulnerabilities(character)
    if not carried:
        return []
    triggers = ControlLossTrigger.objects.filter(
        vulnerability_id__in=carried, fires_on=fires_on
    ).select_related("check_type", "relief_gift")
    if stage is not None:
        triggers = triggers.filter(stage=stage)
    outcomes: list[ControlLossOutcome] = []
    for trigger in triggers:
        outcome = _fire(character, sheet, trigger, moon_pull=moon_pull)
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


def fire_wound_triggers(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - damage holds characters
    *,
    health_before: int,
    health_after: int,
    max_health: int,
) -> list[ControlLossOutcome]:
    """Fire each WOUND_THRESHOLD trigger whose threshold this hit crossed downward.

    A threshold of N percent is crossed when ``health_before >= N% of max_health >
    health_after``. Nothing is stored between hits: each downward crossing fires. A
    character who cannot act (``can_act``) rolls nothing; the damage service already
    leaves out a killing hit. A hit into the knockout band rolls while the character can
    still act: the knockout check for that hit is rolled afterwards by its caller.
    """
    if max_health <= 0 or health_after >= health_before:
        return []
    from world.conditions.models import ControlLossTrigger  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    sheet = _roller_sheet(character)
    if sheet is None:
        return []
    carried = _carried_vulnerabilities(character)
    if not carried or not can_act(sheet):
        return []
    outcomes: list[ControlLossOutcome] = []
    for trigger in ControlLossTrigger.objects.filter(
        vulnerability_id__in=carried, fires_on=ControlLossFiresOn.WOUND_THRESHOLD
    ).select_related("check_type", "relief_gift"):
        line = trigger.health_below_percent * max_health
        if health_before * 100 >= line > health_after * 100:
            outcome = _fire(character, sheet, trigger)
            if outcome is not None:
                outcomes.append(outcome)
    return outcomes


def fire_stage_triggers(instance: ConditionInstance) -> list[ControlLossOutcome]:
    """Fire the CONDITION_STAGE triggers of *instance*'s condition for the stage it is in."""
    if instance.current_stage_id is None:
        return []
    return fire_control_loss_triggers(
        instance.target,
        ControlLossFiresOn.CONDITION_STAGE,
        stage=instance.current_stage,
    )


def _carried_vulnerabilities(character: ObjectDB) -> set[int]:  # noqa: OBJECTDB_PARAM
    """The condition ids *character* carries, or none when a compulsion already drives them.

    Every trigger path (moon, wound, stage) skips a character who is already compelled
    (ruled 2026-10-31): a raging character does not re-roll on each crossing, and the
    compulsion they are under runs its course.
    """
    instances = character.conditions.active()
    if not instances or active_compulsion(character, instances) is not None:
        return set()
    return {inst.condition_id for inst in instances}


def display_name_of(character: ObjectDB) -> str:  # noqa: OBJECTDB_PARAM
    """The persona name others know *character* by; the key when there is no sheet."""
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return character.key
    return persona_names_for_sheets([sheet.pk]).get(sheet.pk, character.key)


def _roller_sheet(character: ObjectDB) -> CharacterSheet | None:  # noqa: OBJECTDB_PARAM
    """The sheet of a character who rolls: a player character only (NPCs are targets)."""
    from typeclasses.characters import Character  # noqa: PLC0415
    from world.roster.services.activity import is_player_character  # noqa: PLC0415

    if not isinstance(character, Character):
        return None
    sheet = character.character_sheet
    if sheet is None or not is_player_character(sheet):
        return None
    return sheet


def _fire(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    sheet: CharacterSheet,
    trigger: ControlLossTrigger,
    *,
    moon_pull: int = 0,
) -> ControlLossOutcome | None:
    """Roll one trigger and apply its band. None when the trigger does not roll."""
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415

    if trigger.fires_on == ControlLossFiresOn.MOON_PULL and (
        moon_pull <= 0 or moon_pull < (trigger.min_moon_pull or 0)
    ):
        return None
    level = sheet.current_level
    if (
        trigger.exempt_from_level is not None
        and level >= trigger.exempt_from_level
        and not _is_impaired(sheet, trigger)
    ):
        return None
    result = perform_check_with_modifiers(
        character,
        trigger.check_type,
        target_difficulty=_difficulty(sheet, trigger, moon_pull=moon_pull, level=level),
        extra_traits=_skill_terms(trigger),
    )
    band = _band_for(trigger, result)
    applied = _apply_band(character, sheet, band) if band is not None else None
    if band is not None and (applied is not None or band.control_change or band.intensity):
        _announce(character, trigger, result, applied)
    return ControlLossOutcome(trigger=trigger, check_result=result, band=band, applied=applied)


def _difficulty(
    sheet: CharacterSheet, trigger: ControlLossTrigger, *, moon_pull: int, level: int
) -> int:
    """base + per-pull * pull - per-level * level - thread relief, floored at 0."""
    total = (
        trigger.base_difficulty
        + (trigger.difficulty_per_pull or 0) * moon_pull
        - trigger.relief_per_level * level
        - _thread_relief(sheet, trigger)
    )
    return max(0, total)


def _thread_relief(sheet: CharacterSheet, trigger: ControlLossTrigger) -> int:
    """Relief from the character's thread on the trigger's relief gift, capped."""
    from world.magic.models import Thread  # noqa: PLC0415

    if trigger.relief_gift_id is None or not trigger.relief_per_thread_level:
        return 0
    thread = (
        Thread.objects.filter(
            owner=sheet, target_gift_id=trigger.relief_gift_id, retired_at__isnull=True
        )
        .order_by("pk")
        .first()
    )
    if thread is None:
        return 0
    relief = thread.level * trigger.relief_per_thread_level
    return relief if trigger.relief_cap is None else min(trigger.relief_cap, relief)


def _is_impaired(sheet: CharacterSheet, trigger: ControlLossTrigger) -> bool:
    """Condition-driven willpower at or below ``-impaired_willpower_drop`` (ruled 2026-07-31)."""
    from world.conditions.services import get_condition_modifier_total  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.traits.constants import PrimaryStat, TraitType  # noqa: PLC0415

    if not trigger.impaired_willpower_drop:
        return False
    target = (
        ModifierTarget.objects.filter(
            target_trait__name=PrimaryStat.WILLPOWER, target_trait__trait_type=TraitType.STAT
        )
        .order_by("pk")
        .first()
    )
    if target is None:
        return False
    return get_condition_modifier_total(sheet, target) <= -trigger.impaired_willpower_drop


def _skill_terms(trigger: ControlLossTrigger) -> tuple:
    """Magic skills staff mapped to the moon-control activity ride the moon's roll.

    Moon-only today: ``MagicActivity.MOON_CONTROL`` is the one activity slot that maps to a
    trigger kind, so wound and stage triggers carry no skill terms.
    """
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    if trigger.fires_on != ControlLossFiresOn.MOON_PULL:
        return ()
    return tuple(activity_skill_terms(MagicActivity.MOON_CONTROL))


def _band_for(trigger: ControlLossTrigger, result: CheckResult) -> ControlLossBand | None:
    """The trigger's band for the roll's outcome, if staff authored one."""
    if result.outcome is None:
        return None
    bands = trigger.bands.filter(outcome_id=result.outcome.pk)
    return bands.select_related("applies").order_by("pk").first()


def _apply_band(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    sheet: CharacterSheet,
    band: ControlLossBand,
) -> ConditionInstance | None:
    """Apply a band: engagement shift, forced form, then the condition it names."""
    from world.conditions.services import apply_condition  # noqa: PLC0415

    if band.intensity or band.control_change:
        _shift_engagement_of(character, band)
    if band.forces_form:
        _force_battle_form_shift(character, sheet)
    if band.applies is None:
        return None
    return apply_condition(
        character,
        band.applies,
        severity=band.severity,
        duration_rounds=band.duration_rounds,
        source_character=character,
    ).instance


def _shift_engagement_of(character: ObjectDB, band: ControlLossBand) -> None:  # noqa: OBJECTDB_PARAM
    """Land the band's intensity and control on the character's engagement, if any."""
    from world.magic.services.fury import engagement_of, shift_engagement  # noqa: PLC0415

    engagement = engagement_of(character)
    if engagement is None:
        return
    shift_engagement(
        engagement, intensity=band.intensity, control=band.control_change, surrendered=0
    )


def _announce(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    trigger: ControlLossTrigger,
    result: CheckResult,
    applied: ConditionInstance | None,
) -> None:
    """Tell the character and the room a roll moved their control or applied a condition.

    The room hears the persona name the rest of combat uses, never the character key.
    Inside a combat round (the character's encounter is RESOLVING: a wound from a swing,
    a stage reached by the round tick) the line goes out as one of the round's narration
    rows, so it persists in the scene log and keeps its place among the round's lines;
    the character reads the same row. Outside a round both lines go out once the
    surrounding transaction commits (a hit that rolls back tells nobody about a roll
    that never happened).
    """
    from django.db import transaction  # noqa: PLC0415

    outcome = result.outcome.name
    check = trigger.check_type.name
    name = display_name_of(character)
    seen = f"{name} fights to keep control. {check}: {outcome}." + (
        f" {name} loses control: {applied.condition.name}." if applied is not None else ""
    )
    encounter = _resolving_encounter_of(character)
    if encounter is not None:
        _narrate_in_round(encounter, character, seen)
        return
    own = f"You fight to keep control. {check}: {outcome}." + (
        f" You lose control: {applied.condition.name}." if applied is not None else ""
    )
    room = character.location
    transaction.on_commit(lambda: character.msg("|r" + own + "|n"))
    if room is not None:
        transaction.on_commit(lambda: room.msg_contents("|r" + seen + "|n", exclude=[character]))


def _resolving_encounter_of(character: ObjectDB) -> CombatEncounter | None:  # noqa: OBJECTDB_PARAM
    """The encounter *character* sits in whose round is resolving now, if any."""
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return None
    seat = (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            encounter__status=RoundStatus.RESOLVING,
        )
        .select_related("encounter")
        .order_by("pk")
        .first()
    )
    return seat.encounter if seat is not None else None


def _narrate_in_round(
    encounter: CombatEncounter,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    line: str,
) -> None:
    """Send a trigger line as a round narration row, the seam the compulsion lines use.

    With no room the row is still kept in the scene log and the character is told directly.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(encounter=encounter, narration=line, target_personas=[])
    if encounter.room is None:
        character.msg(line)


def _force_battle_form_shift(character: ObjectDB, sheet: CharacterSheet) -> None:  # noqa: OBJECTDB_PARAM
    """Shift into the battle form via the built involuntary seam, moon-scaled.

    Moon-only today: the battle form is the lycan's, provisioned by ``moon_provisioning``,
    and ``ControlLossBand.clean`` allows ``forces_form`` on a moon-pull trigger only.

    Skips silently when an alternate self is already active (a voluntary shift preempts the
    forced one: the rage takes over the shape they already wear). A missing battle form is
    provisioned first.
    """
    from world.forms.models import ActiveAlternateSelf, AlternateSelf  # noqa: PLC0415
    from world.forms.services.transformation import trigger_transformation  # noqa: PLC0415
    from world.species.moon_provisioning import ensure_lycan_battle_form  # noqa: PLC0415
    from world.species.moon_pull import moon_clarity_instance_value  # noqa: PLC0415

    if ActiveAlternateSelf.objects.filter(character=sheet).exists():
        return
    alt = (
        AlternateSelf.objects.filter(character=sheet, combat_profile__isnull=False)
        .order_by("pk")
        .first()
    )
    if alt is None:
        alt = ensure_lycan_battle_form(sheet)
    clarity = moon_clarity_instance_value(character, character.location)
    trigger_transformation(sheet, alt, cause="moon", instance_value=clarity)
