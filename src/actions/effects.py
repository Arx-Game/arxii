"""Standard enhancement effect applicators.

This module interprets ``ActionEnhancement.effect_parameters`` and modifies
the ``ActionContext`` accordingly. New effect types are added here as functions,
keeping enhancement behavior data-driven — add rows to ActionEnhancement,
not code to source models.

Standard effect vocabulary in ``effect_parameters``:

- ``modify_kwargs``: dict mapping kwarg names to transform names.
    Example: ``{"text": "uppercase"}`` → uppercases ``context.kwargs["text"]``.
- ``add_modifiers``: dict merged into ``context.modifiers``.
    Example: ``{"check_bonus": 5}`` → ``context.modifiers["check_bonus"] = 5``.
- ``post_effect``: str naming a registered post-effect type.
    Remaining keys in effect_parameters are passed as parameters.
    Example: ``{"post_effect": "charm_check", "charm_strength": 3}``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from actions.types import ActionContext

# === Kwarg transforms ===

KWARG_TRANSFORMS: dict[str, callable] = {
    "uppercase": lambda value: value.upper() if isinstance(value, str) else value,
    "lowercase": lambda value: value.lower() if isinstance(value, str) else value,
}


def _apply_modify_kwargs(context: ActionContext, modifications: dict[str, str]) -> None:
    """Apply named transforms to kwargs values."""
    for kwarg_name, transform_name in modifications.items():
        transform = KWARG_TRANSFORMS.get(transform_name)
        if transform and kwarg_name in context.kwargs:
            context.kwargs[kwarg_name] = transform(context.kwargs[kwarg_name])


# === Post-effect types ===


def _charm_check_post_effect(context: ActionContext, parameters: dict[str, Any]) -> None:
    """Post-effect: apply a charm check against the target after action execution."""
    target = context.target
    if target is None or context.result is None:
        return

    context.result.data.setdefault("post_effects_applied", []).append(
        {
            "type": "charm_check",
            "target": target,
            "charm_strength": parameters.get("charm_strength", 1),
            "action_succeeded": context.result.success,
        }
    )


POST_EFFECT_TYPES: dict[str, callable] = {
    "charm_check": _charm_check_post_effect,
}


def _apply_post_effect(
    context: ActionContext,
    effect_type: str,
    parameters: dict[str, Any],
) -> None:
    """Queue a named post-effect to run after execution."""
    handler = POST_EFFECT_TYPES.get(effect_type)
    if handler:
        context.post_effects.append(lambda ctx: handler(ctx, parameters))


# === Main entry point ===


def apply_standard_effects(context: ActionContext, effect_parameters: dict[str, Any]) -> None:
    """Interpret effect_parameters and modify the ActionContext.

    Called by ``ActionEnhancement.apply()``.
    """
    if modify_kwargs := effect_parameters.get("modify_kwargs"):
        _apply_modify_kwargs(context, modify_kwargs)

    if add_modifiers := effect_parameters.get("add_modifiers"):
        context.modifiers.update(add_modifiers)

    if post_effect := effect_parameters.get("post_effect"):
        # Everything except the known keys is passed as parameters to the post-effect
        params = {
            k: v
            for k, v in effect_parameters.items()
            if k not in ("modify_kwargs", "add_modifiers", "post_effect")
        }
        _apply_post_effect(context, post_effect, params)
