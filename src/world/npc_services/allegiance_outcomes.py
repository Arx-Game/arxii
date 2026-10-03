"""How an allegiance hold ends when someone acts, or when no one does (#4091).

Settle (Decision 17) and break (Decision 16) both end the hold through the
condition's settle pool at the acting PC's roll tier, then remove the condition
through ``remove_condition`` so the removal event fires. No result ever starts a
fight (Decision 21). A hold that runs out with nobody acting simply ends (sweep).
"""

from __future__ import annotations

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
    from world.checks.types import CheckResult
    from world.combat.models import CombatOpponent
    from world.conditions.models import ConditionInstance
    from world.scenes.models import Scene


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


def attempt_allegiance_break(
    *,
    striker: CharacterSheet,
    opponent: CombatOpponent,
    damage_dealt: int,
    extra_pressure: int = 0,
) -> AllegianceBreakResult | None:
    """Decision 16: the PC who harms a held NPC rolls to break the hold.

    Difficulty = hold strength - the NPC's resistance - the harm's pressure, floored
    at 0. A strong hold on a weak NPC is hard to break; a faded hold on a strong-
    willed NPC breaks easily. Success ends the hold through its settle pool at the
    striker's tier. Failure: the hold stands and the NPC does not fight back.
    """
    from world.checks.services import compute_resist_increment, perform_check  # noqa: PLC0415
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415
    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

    if opponent.objectdb_id is None or damage_dealt <= 0:
        return None
    instance = allegiance_instance_on(opponent.objectdb)
    if instance is None:
        return None
    strength = charm_strength_points(instance)
    resistance = compute_resist_increment(
        opponent.objectdb, EffortLevel.MEDIUM, level_override=opponent.level
    )
    pressure = harm_pressure_points(damage_dealt, opponent.max_health) + extra_pressure
    difficulty = max(0, strength - resistance - pressure)
    check_result = perform_check(
        striker.character,
        instance.condition.allegiance_break_check_type,
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
