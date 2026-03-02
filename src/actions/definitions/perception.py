"""Perception-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class LookAction(Action):
    """Look at a target entity to get its description."""

    key: str = "look"
    name: str = "Look"
    icon: str = "eye"
    category: str = "perception"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_look"
    result_event: str | None = "look"

    def execute(self, actor: ObjectDB, **kwargs: Any) -> ActionResult:  # noqa: ARG002
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Look at what?")

        sdm = SceneDataManager()
        target_state = sdm.initialize_state_for_object(target)
        description = target_state.return_appearance(mode="look")

        return ActionResult(
            success=True,
            message=description,
        )


@dataclass
class InventoryAction(Action):
    """View the character's inventory."""

    key: str = "inventory"
    name: str = "Inventory"
    icon: str = "backpack"
    category: str = "perception"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, **kwargs: Any) -> ActionResult:  # noqa: ARG002
        sdm = SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        items = caller_state.contents
        if not items:
            return ActionResult(success=True, message="You are not carrying anything.")

        names = [it.get_display_name(looker=caller_state) for it in items]
        text = "You are carrying: " + ", ".join(names)
        return ActionResult(success=True, message=text)
