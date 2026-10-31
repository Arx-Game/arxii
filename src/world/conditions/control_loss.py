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
from world.conditions.types import ControlLossOutcome

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.conditions.models import (
        Compulsion,
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
    from world.conditions.models import Compulsion  # noqa: PLC0415

    if active_instances is None:
        active_instances = character.conditions.active()
    instances = {inst.condition_id: inst for inst in active_instances}
    if not instances:
        return None
    best: tuple[Compulsion, ConditionInstance] | None = None
    for compulsion in Compulsion.objects.filter(condition_id__in=instances):
        instance = instances[compulsion.condition_id]
        if best is None or (instance.severity, -instance.pk) > (best[1].severity, -best[1].pk):
            best = (compulsion, instance)
    return best


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
    carried = {inst.condition_id for inst in character.conditions.active()}
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
    health_after``. Nothing is stored between hits: each downward crossing fires.
    """
    if max_health <= 0 or health_after >= health_before:
        return []
    from world.conditions.models import ControlLossTrigger  # noqa: PLC0415

    sheet = _roller_sheet(character)
    if sheet is None:
        return []
    carried = {inst.condition_id for inst in character.conditions.active()}
    if not carried:
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
    """Tell the character and the room a roll moved their control or applied a condition."""
    outcome = result.outcome.name
    check = trigger.check_type.name
    lost = f" {{who}} lose control: {applied.condition.name}." if applied is not None else ""
    base = f"{{who}} fight to keep control. {check}: {outcome}."
    character.msg("|r" + (base + lost).format(who="You") + "|n")
    room = character.location
    if room is not None:
        text = f"{character.key} fights to keep control. {check}: {outcome}." + (
            f" {character.key} loses control: {applied.condition.name}." if applied else ""
        )
        room.msg_contents("|r" + text + "|n", exclude=[character])


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
