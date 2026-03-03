"""Handler registry and dispatch for effect configs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import ActionEnhancement
    from actions.types import ActionContext


def apply_effects(enhancement: ActionEnhancement, context: ActionContext) -> None:
    """Query all effect configs for this enhancement and dispatch to handlers.

    Placeholder — will be implemented in Task 6.
    """
