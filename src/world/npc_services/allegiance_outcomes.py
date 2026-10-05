"""How an allegiance hold ends when someone acts, or when no one does (#4091).

Settle (Decision 17) and break (Decision 16) both end the hold through the
condition's settle pool at the acting PC's roll tier, then remove the condition
through ``remove_condition`` so the removal event fires. No result ever starts a
fight (Decision 21). A hold that runs out with nobody acting ends in the sweep:
plainly, or (#4120, a hold with a PC charmer) after one warning and an auto-rolled
break check at the charmer's tier.

Break's difficulty (``attempt_allegiance_break``) is::

    difficulty = max(0, strength - resistance - pressure)
    strength   = severity points (charm_strength_points) + caster level opposition
                 (_caster_level_opposition_points)
    resistance = the target's own level/traits opposing the break (compute_resist_increment)
    pressure   = the harm's post-soak damage, scaled by the target's max health
                 (harm_pressure_points)

Both sides of the hold count a level now (fix round 2): the caster's level raises
strength, the target's level raises resistance (which LOWERS difficulty -- a
strong-willed target is already straining against the hold internally, so a PC's
blow has less work left to do). Before fix round 2, only the target's level
counted, so any opponent roughly level 12+ zeroed a mid-severity hold's difficulty
regardless of who cast it or how hard the PC hit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierContribution
from world.npc_services.constants import (
    BREAK_PRESSURE_POINTS_PER_TENTH_HEALTH,
    CHARM_STRENGTH_POINTS_PER_SEVERITY,
)
from world.npc_services.types import AllegianceBreakResult, AllegianceEnding

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.combat.models import CombatOpponent
    from world.conditions.models import ConditionInstance
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


def charm_strength_points(instance: ConditionInstance) -> int:
    """The hold's current strength in check points (severity x stage multiplier)."""
    return instance.effective_severity * CHARM_STRENGTH_POINTS_PER_SEVERITY


def settle_pool_for(instance: ConditionInstance) -> ConsequencePool | None:
    stage = instance.current_stage
    if stage is not None and stage.settle_consequence_pool_id is not None:
        return stage.settle_consequence_pool
    return instance.condition.settle_consequence_pool


def _strength_label(instance: ConditionInstance) -> str:
    stage = instance.current_stage
    name = instance.condition.name
    return f"Charm strength ({name}, {stage.name})" if stage else f"Charm strength ({name})"


def settle_contributions(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - an NPC body; the pipeline hands an ObjectDB
) -> list[ModifierContribution]:
    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415

    instance = allegiance_instance_on(target)
    if instance is None:
        return []
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.CONDITION,
            source_label=_strength_label(instance),
            value=charm_strength_points(instance),
        )
    ]


def end_allegiance_with_pool(
    instance: ConditionInstance,
    *,
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the acting PC's character, as ResolutionContext takes
    check_result: CheckResult,
    scene: Scene | None = None,
) -> AllegianceEnding:
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target = instance.target
    condition = instance.condition
    label: str | None = None
    pool = settle_pool_for(instance)
    if pool is not None:
        pending = select_consequence_from_result(actor, check_result, pool.cached_consequences)
        apply_resolution(pending, ResolutionContext(character=actor, target=target, scene=scene))
        # An unsaved sentinel (no authored row for this tier, e.g. no botch row in
        # the pool) carries no real pk -- never narrate its synthetic label.
        if pending.selected_consequence.pk is not None:
            label = pending.selected_consequence.label or None
    remove_condition(target, condition)
    if target.location is not None and condition.is_visible_to_others:
        # PLACEHOLDER: the target's presented face (#981), never target.key when one
        # is available -- R2 guarantees Settle always targets a persona, but Break
        # (#4091 task 9) reaches here for an ephemeral, persona-less combat mook too,
        # so this falls back to the ObjectDB's own key rather than crashing on a
        # None character_sheet.
        sheet = target.character_sheet  # type: ignore[attr-defined] -- typeclass extension
        name = active_persona_for_sheet(sheet).name if sheet is not None else target.key
        text = label or f"The {condition.name} on {name} ends."
        narrate_room_outcome(target.location, text)
    return AllegianceEnding(condition_name=condition.name, consequence_label=label)


def settle_allegiance(
    *,
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - an NPC body
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the settling PC's character
    check_result: CheckResult,
    scene: Scene | None = None,
) -> AllegianceEnding | None:
    """Decision 17: an active settle ends the hold at the settler's tier."""
    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415

    instance = allegiance_instance_on(target)
    if instance is None:
        return None
    return end_allegiance_with_pool(instance, actor=actor, check_result=check_result, scene=scene)


def harm_pressure_points(damage: int, max_health: int) -> int:
    """One pressure step per tenth of max health lost in the hit (PLACEHOLDER scale)."""
    return (max(0, damage) * 10 // max(1, max_health)) * BREAK_PRESSURE_POINTS_PER_TENTH_HEALTH


def _caster_level_opposition_points(instance: ConditionInstance, check_type: CheckType) -> int:
    """The hold's own caster's level opposing an attempt to break it (#4091 fix round 2).

    Without this, the break difficulty only counted the TARGET's level (via
    resistance) and never the CASTER's -- one-sided, so a high-enough-level target
    zeroed the difficulty out regardless of how strong a hold its own (possibly
    low-level) charmer cast. Reuses the identical pattern
    ``attempt_break_free`` (``world/conditions/services.py``) already uses for
    exactly this term -- ``level_opposition``/``get_character_path_level`` verbatim,
    never a parallel formula.

    0 when the hold has no ``source_character`` (a REAL case: the charmer left the
    game or was deleted, not a defensive guard) or when that character has no
    ``CharacterSheet`` (sheetless) -- deliberately NOT the level-1 floor
    ``get_character_path_level`` would otherwise return for an unresolvable
    character, since an unknown/gone caster contributes no real opposition.
    """
    caster = instance.source_character
    if caster is None or caster.character_sheet is None:  # type: ignore[attr-defined]
        return 0
    from world.checks.services import level_opposition  # noqa: PLC0415
    from world.progression.services.skill_development import (  # noqa: PLC0415
        get_character_path_level,
    )

    return level_opposition(check_type, level=get_character_path_level(caster), character=caster)


def attempt_allegiance_break(
    *,
    striker: CharacterSheet,
    opponent: CombatOpponent,
    damage_dealt: int,
    extra_pressure: int = 0,
    instance: ConditionInstance | None = None,
) -> AllegianceBreakResult | None:
    """Decision 16: the PC who harms a held NPC rolls to break the hold.

    Difficulty = hold strength - the NPC's resistance - the harm's pressure, floored
    at 0, where strength = severity points + the hold's own caster's level
    opposition (fix round 2 -- see ``_caster_level_opposition_points``). A strong
    hold (high severity, cast by a high-level caster) on a weak NPC is hard to
    break; a faded hold cast by a low-level caster on a strong-willed NPC breaks
    easily. Success ends the hold through its settle pool at the striker's tier.
    Failure: the hold stands and the NPC does not fight back.

    ``instance`` is the opponent's designating allegiance instance when the caller
    already fetched it in a batch (``_attempt_allegiance_breaks_for_action``);
    omitted, it is looked up here.

    A hold whose condition has no ``allegiance_break_check_type`` is missing
    content: no roll is made, the hold persists, and one warning names the
    condition (#4091 final review ruling). Raising here would roll back the whole
    atomic ``resolve_round`` and the round timer would retry it forever, leaving
    the encounter stuck. The REQUIRED ``allegiance-break-check`` dashboard row is
    the sentinel that tells staff to fill it in.
    """
    from world.checks.services import compute_resist_increment, perform_check  # noqa: PLC0415
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415
    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

    if opponent.objectdb_id is None or damage_dealt <= 0:
        return None
    if instance is None:
        instance = allegiance_instance_on(opponent.objectdb)
    if instance is None:
        return None
    check_type = instance.condition.allegiance_break_check_type
    if check_type is None:
        logger.warning(
            "Allegiance condition %r (pk=%s) has no allegiance_break_check_type; "
            "skipping the break roll, the hold persists.",
            instance.condition.name,
            instance.condition_id,
        )
        return None
    strength = charm_strength_points(instance) + _caster_level_opposition_points(
        instance, check_type
    )
    resistance = compute_resist_increment(
        opponent.objectdb, EffortLevel.MEDIUM, level_override=opponent.level
    )
    pressure = harm_pressure_points(damage_dealt, opponent.max_health) + extra_pressure
    difficulty = max(0, strength - resistance - pressure)
    check_result = perform_check(
        striker.character,
        check_type,
        target_difficulty=difficulty,
    )
    broke = check_result.outcome is not None and check_result.outcome.success_level > 0
    ending = None
    if broke:
        ending = end_allegiance_with_pool(
            instance, actor=striker.character, check_result=check_result
        )
    elif opponent.objectdb.location is not None and instance.condition.is_visible_to_others:
        narrate_room_outcome(
            opponent.objectdb.location,
            # PLACEHOLDER player prose (#4091).
            f"The {instance.condition.name} on {opponent.name} holds through the blow.",
        )
    return AllegianceBreakResult(
        condition_name=instance.condition.name,
        difficulty=difficulty,
        strength=strength,
        resistance=resistance,
        pressure=pressure,
        broke=broke,
        ending=ending,
    )


def _charmer_with_account(instance: ConditionInstance) -> ObjectDB | None:
    """The hold's charmer when it is a played character (has an account), else None."""
    charmer = instance.source_character
    if charmer is None or charmer.db_account is None:
        return None
    return charmer


def _target_name(instance: ConditionInstance) -> str:
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    target = instance.target
    return persona_names_for_sheets([target.pk]).get(target.pk, target.key)


def warn_fading_allegiance(instance: ConditionInstance) -> None:
    """Tell the charmer, once, that their hold is about to run out (#4120).

    Only the charmer's own character hears it; the stamp keeps the sweep from
    repeating it every minute.
    """
    from django.utils import timezone  # noqa: PLC0415

    charmer = _charmer_with_account(instance)
    if charmer is None:
        return
    # PLACEHOLDER player prose (#4120), like the R6 system lines.
    charmer.msg(f"The {instance.condition.name} on {_target_name(instance)} is fading.")
    instance.lapse_warned_at = timezone.now()
    instance.save(update_fields=["lapse_warned_at"])


def auto_settle_lapsed_allegiance(instance: ConditionInstance) -> bool:
    """End a lapsed hold through an auto-rolled check by its PC charmer (#4120).

    Returns False when the hold has no played charmer or its condition has no
    ``allegiance_break_check_type`` (missing content: one warning, the caller falls
    back to plain removal). Never opens an encounter or any hostility (Decision 21).
    The check difficulty (the hold's strength points) is PLACEHOLDER tuning (#4120).
    """
    from world.checks.services import perform_check  # noqa: PLC0415

    charmer = _charmer_with_account(instance)
    if charmer is None:
        return False
    check_type = instance.condition.allegiance_break_check_type
    if check_type is None:
        logger.warning(
            "Allegiance condition %r (pk=%s) has no allegiance_break_check_type; "
            "skipping the lapse roll, the hold is removed plainly.",
            instance.condition.name,
            instance.condition_id,
        )
        return False
    # PLACEHOLDER tuning (#4120): difficulty is just the hold's strength points.
    check_result = perform_check(
        charmer, check_type, target_difficulty=max(0, charm_strength_points(instance))
    )
    end_allegiance_with_pool(instance, actor=charmer, check_result=check_result)
    return True


def lapsed_allegiance_sweep() -> None:
    """Warn on fading allegiance holds and settle lapsed ones (Decisions 17, 18, 21).

    The "no roll and no pool" clause of Decisions 17 and 18 is superseded by #4120
    for holds with a PC charmer: that charmer is warned once in the
    ``lapse_warning_seconds`` window before expiry, and at lapse an auto-rolled
    check settles the hold through its pool. A hold with no PC charmer (or no check
    type) is removed plainly. The no-fight rule (Decision 21) stands: the NPC
    returns to its old stance, nothing attacks, and no encounter opens (#4121
    decides when a lapsed NPC turns hostile; a GM can start a fight by hand).
    Removal goes through ``remove_condition`` so CONDITION_REMOVED fires. Also closes
    bind windows whose charmer has left (Decision 19) -- this is also how a kept
    nameless charmed NPC gets deleted once its window closes (#4091 task 7).

    Runs every minute (``combat.lapsed_allegiance_sweep``) and owns every
    ``sets_allegiance``-bearing ``ConditionInstance``; the hourly
    ``batch_condition_expiration_cleanup`` (``world/game_clock/tasks.py``) skips those
    rows so its bulk ``.delete()`` never silently drops the removal event this sweep
    fires per row.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.combat.won_over import release_closed_bind_windows  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import get_settle_config, remove_condition  # noqa: PLC0415
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    now = timezone.now()
    window = timedelta(seconds=get_settle_config().lapse_warning_seconds)
    fading = (
        ConditionInstance.objects.filter(
            expires_at__gt=now, expires_at__lte=now + window, lapse_warned_at__isnull=True
        )
        .exclude(condition__sets_allegiance="")
        .select_related("condition", "target")
    )
    for instance in list(fading):
        warn_fading_allegiance(instance)

    expired = list(
        ConditionInstance.objects.filter(expires_at__lt=now)
        .exclude(condition__sets_allegiance="")
        .select_related("condition", "target")
    )
    # Batched: CharacterSheet shares ObjectDB's pk (CLAUDE.md), so each target's own
    # pk IS its sheet id -- no need to fetch the sheet first, and no per-instance
    # persona query. A target with no sheet (an ephemeral combat mook) is simply
    # absent from the map, so it falls back to the ObjectDB's own key, which equals
    # that mook's CombatOpponent.name.
    persona_names = persona_names_for_sheets(instance.target_id for instance in expired)
    for instance in expired:
        if auto_settle_lapsed_allegiance(instance):
            continue
        target = instance.target
        condition = instance.condition
        room = target.location
        remove_condition(target, condition)
        if room is not None and condition.is_visible_to_others:
            name = persona_names.get(target.pk, target.key)
            # R6: PLACEHOLDER system line (#4091).
            narrate_room_outcome(room, f"The {condition.name} on {name} has run out.")
    release_closed_bind_windows()
