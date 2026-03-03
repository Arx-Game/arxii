"""Handler for AddModifierConfig effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import AddModifierConfig
    from actions.types import ActionContext


def handle_add_modifier(context: ActionContext, config: AddModifierConfig) -> None:
    """Set a key-value modifier in context.modifiers."""
    context.modifiers[config.modifier_key] = config.modifier_value
