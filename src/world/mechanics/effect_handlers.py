"""Handlers for applying consequence effects from challenge resolution."""

import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.constants import EffectTarget, EffectType
from world.codex.models import CharacterCodexKnowledge
from world.conditions.services import apply_condition, remove_condition
from world.mechanics.models import ObjectProperty
from world.mechanics.types import AppliedEffect
from world.vitals.services import process_damage_consequences

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import Consequence, ConsequenceEffect
    from world.checks.types import ResolutionContext

logger = logging.getLogger(__name__)

_SKIP_ATTACK = "Attack system not yet implemented."


def apply_effect(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Dispatch a single ConsequenceEffect and return the result."""
    handler = _HANDLER_REGISTRY.get(effect.effect_type)
    if handler is None:
        return AppliedEffect(
            effect_type=effect.effect_type,
            description="",
            applied=False,
            skip_reason=f"No handler for effect type {effect.effect_type}",
        )
    return handler(effect, context)


def apply_all_effects(
    consequence: "Consequence",
    context: "ResolutionContext",
) -> list[AppliedEffect]:
    """Apply all effects on a consequence. Returns empty list for unsaved consequences."""
    if consequence.pk is None:
        return []
    effects = consequence.effects.all().order_by("execution_order")
    return [apply_effect(e, context) for e in effects]


def _resolve_target(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> "ObjectDB":
    """Resolve the target ObjectDB for an effect based on EffectTarget."""
    if effect.target == EffectTarget.TARGET:
        return context.target if context.target is not None else context.character
    if effect.target == EffectTarget.LOCATION:
        return context.location
    return context.character


# ---------------------------------------------------------------------------
# Individual effect handlers
# ---------------------------------------------------------------------------


def _apply_condition(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply a condition to the resolved target."""
    target = _resolve_target(effect, context)
    severity = effect.condition_severity or 1
    apply_condition(target, effect.condition_template, severity=severity)
    condition_name = effect.condition_template.name
    return AppliedEffect(
        effect_type=EffectType.APPLY_CONDITION,
        description=f"Applied {condition_name} (severity {severity}) to {target.db_key}",
        applied=True,
    )


def _remove_condition(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Remove a condition from the resolved target."""
    target = _resolve_target(effect, context)
    removed = remove_condition(target, effect.condition_template)
    condition_name = effect.condition_template.name
    if removed:
        description = f"Removed {condition_name} from {target.db_key}"
    else:
        description = f"{condition_name} was not present on {target.db_key}"
    return AppliedEffect(
        effect_type=EffectType.REMOVE_CONDITION,
        description=description,
        applied=True,
    )


def _add_property(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Add or update an ObjectProperty on the resolved target."""
    target = _resolve_target(effect, context)
    value = effect.property_value or 1
    obj_prop, _ = ObjectProperty.objects.update_or_create(
        object=target,
        property=effect.property,
        defaults={"value": value},
    )
    prop_name = effect.property.name
    return AppliedEffect(
        effect_type=EffectType.ADD_PROPERTY,
        description=f"Added property {prop_name} ({value}) to {target.db_key}",
        applied=True,
        created_instance=obj_prop,
    )


def _remove_property(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Remove an ObjectProperty from the resolved target."""
    target = _resolve_target(effect, context)
    deleted_count, _ = ObjectProperty.objects.filter(
        object=target,
        property=effect.property,
    ).delete()
    prop_name = effect.property.name
    if deleted_count:
        description = f"Removed property {prop_name} from {target.db_key}"
    else:
        description = f"Property {prop_name} was not present on {target.db_key}"
    return AppliedEffect(
        effect_type=EffectType.REMOVE_PROPERTY,
        description=description,
        applied=True,
    )


def _deal_damage(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply damage to target's health and trigger survivability pipeline."""
    target = _resolve_target(effect, context)
    if target is None:
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="No target to damage",
            applied=False,
            skip_reason="Target not found",
        )

    try:
        vitals = target.sheet_data.vitals
    except (AttributeError, ObjectDoesNotExist):
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="Target has no vitals",
            applied=False,
            skip_reason="Target has no CharacterVitals",
        )

    vitals.health -= effect.damage_amount
    vitals.save(update_fields=["health"])

    process_damage_consequences(
        character=target,
        damage_dealt=effect.damage_amount,
        damage_type=effect.damage_type,
    )

    damage_type_name = effect.damage_type.name if effect.damage_type else "untyped"
    return AppliedEffect(
        effect_type=EffectType.DEAL_DAMAGE,
        description=f"Dealt {effect.damage_amount} {damage_type_name} damage",
        applied=True,
    )


def _launch_attack(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",  # noqa: ARG001
) -> AppliedEffect:
    """Stub handler for attack effects — awaiting combat system."""
    return AppliedEffect(
        effect_type=EffectType.LAUNCH_ATTACK,
        description=f"Would launch attack with {effect.damage_type.name}",
        applied=False,
        skip_reason=_SKIP_ATTACK,
    )


def _launch_flow(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Launch a flow from a consequence effect. Flow engine exists but has no runtime data."""
    flow_name = effect.flow_definition.name if effect.flow_definition else "unknown"
    logger.info(
        "Flow effect triggered: %s for character %s",
        flow_name,
        context.character.db_key,
    )
    return AppliedEffect(
        effect_type=EffectType.LAUNCH_FLOW,
        description=f"Launched flow {flow_name}",
        applied=True,
    )


def _grant_codex(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Grant a codex entry to the character via their RosterEntry."""
    character = context.character
    try:
        roster_entry = character.roster_entry
    except character.roster_entry.RelatedObjectDoesNotExist:
        return AppliedEffect(
            effect_type=EffectType.GRANT_CODEX,
            description="Character has no roster entry",
            applied=False,
            skip_reason="Character has no roster entry",
        )

    _, created = CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=effect.codex_entry,
        defaults={"status": CharacterCodexKnowledge.Status.UNCOVERED},
    )
    entry_name = effect.codex_entry.name
    if created:
        description = f"Granted codex entry: {entry_name}"
    else:
        description = f"Codex entry already known: {entry_name}"
    return AppliedEffect(
        effect_type=EffectType.GRANT_CODEX,
        description=description,
        applied=True,
    )


def _apply_magical_scars(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply a magical scars condition (stub for future alteration system).

    Currently identical to _apply_condition. When the full magical alteration
    system is built, this handler will be replaced to call a resolution function
    that considers the character's resonances, affinity, and Soulfray state.
    """
    target = _resolve_target(effect, context)
    severity = effect.condition_severity or 1
    apply_condition(target, effect.condition_template, severity=severity)
    condition_name = effect.condition_template.name
    return AppliedEffect(
        effect_type=EffectType.MAGICAL_SCARS,
        description=f"Magical scars: {condition_name} (severity {severity}) on {target.db_key}",
        applied=True,
    )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLER_REGISTRY: dict[str, type[None] | object] = {
    EffectType.APPLY_CONDITION: _apply_condition,
    EffectType.REMOVE_CONDITION: _remove_condition,
    EffectType.ADD_PROPERTY: _add_property,
    EffectType.REMOVE_PROPERTY: _remove_property,
    EffectType.DEAL_DAMAGE: _deal_damage,
    EffectType.LAUNCH_ATTACK: _launch_attack,
    EffectType.LAUNCH_FLOW: _launch_flow,
    EffectType.GRANT_CODEX: _grant_codex,
    EffectType.MAGICAL_SCARS: _apply_magical_scars,
}
