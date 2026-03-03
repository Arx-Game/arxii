"""Handler registry and dispatch for effect configs.

Each config model type maps to a handler function. ``apply_effects``
queries all config tables for the given enhancement, merges them by
execution_order, and dispatches each to its handler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.effects.conditions import handle_condition_on_check
from actions.effects.kwargs import handle_modify_kwargs
from actions.effects.modifiers import handle_add_modifier
from actions.models import AddModifierConfig, ConditionOnCheckConfig, ModifyKwargsConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from actions.models import ActionEnhancement
    from actions.types import ActionContext

# Maps config model class → handler function.
# Each handler takes (context, config) and mutates context in-place.
_HANDLER_REGISTRY: dict[type, Callable[[Any, Any], None]] = {
    ModifyKwargsConfig: handle_modify_kwargs,
    AddModifierConfig: handle_add_modifier,
    ConditionOnCheckConfig: handle_condition_on_check,
}

# Related manager names on ActionEnhancement for each config model.
_CONFIG_RELATED_NAMES: list[str] = [
    "modifykwargsconfig_configs",
    "addmodifierconfig_configs",
    "conditiononcheckconfig_configs",
]


def apply_effects(enhancement: ActionEnhancement, context: ActionContext) -> None:
    """Query all effect configs for this enhancement and dispatch to handlers.

    Configs are merged across all config tables and sorted by execution_order
    so that an enhancement with mixed effect types executes in a deterministic order.
    """
    all_configs: list[tuple[int, object]] = []

    for related_name in _CONFIG_RELATED_NAMES:
        manager = getattr(enhancement, related_name, None)
        if manager is not None:
            all_configs.extend((config.execution_order, config) for config in manager.all())

    # Sort by execution_order (stable sort preserves insertion order for ties)
    all_configs.sort(key=lambda pair: pair[0])

    for _order, config in all_configs:
        handler = _HANDLER_REGISTRY.get(type(config))
        if handler is not None:
            handler(context, config)
