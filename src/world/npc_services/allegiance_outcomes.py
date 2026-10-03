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
from world.npc_services.constants import CHARM_STRENGTH_POINTS_PER_SEVERITY
from world.npc_services.types import AllegianceEnding

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance


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
) -> AllegianceEnding:
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

    target = instance.target
    condition = instance.condition
    label: str | None = None
    pool = settle_pool_for(instance)
    if pool is not None:
        pending = select_consequence_from_result(actor, check_result, pool.cached_consequences)
        apply_resolution(pending, ResolutionContext(character=actor, target=target))
        label = pending.selected_consequence.label or None
    remove_condition(target, condition)
    if target.location is not None and condition.is_visible_to_others:
        text = label or f"The {condition.name} on {target.key} ends."
        narrate_room_outcome(target.location, text)
    return AllegianceEnding(condition_name=condition.name, consequence_label=label)


def settle_allegiance(
    *,
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - an NPC body
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the settling PC's character
    check_result: CheckResult,
) -> AllegianceEnding | None:
    """Decision 17: an active settle ends the hold at the settler's tier."""
    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415

    instance = allegiance_instance_on(target)
    if instance is None:
        return None
    return end_allegiance_with_pool(instance, actor=actor, check_result=check_result)
