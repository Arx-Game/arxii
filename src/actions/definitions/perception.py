"""Perception-related actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager

if TYPE_CHECKING:
    from world.items.models import ItemInstance


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

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Look at what?")

        sdm = context.scene_data if context else SceneDataManager()
        target_state = sdm.initialize_state_for_object(target)
        description = target_state.return_appearance(mode="look")

        return ActionResult(
            success=True,
            message=description,
        )


@dataclass
class LookAtItemAction(Action):
    """Examine a specific item — either worn on a character or in a container.

    Dispatched by ``CmdLook`` when the player uses one of the drilled forms:
    ``look bob's hat``, ``look hat on bob``, or ``look coin in pouch``.

    Visibility for worn items is enforced via
    :func:`world.items.services.appearance.visible_worn_items_for` — concealed
    items are hidden from non-self / non-staff observers. Closed containers
    refuse to reveal their contents.
    """

    key: str = "look_at_item"
    name: str = "Examine Item"
    icon: str = "eye"
    category: str = "perception"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_name = kwargs.get("item_name")
        owner_id = kwargs.get("owner_id")
        container_id = kwargs.get("container_id")

        if not item_name:
            return ActionResult(success=False, message="Look at what?")

        if owner_id is None and container_id is None:
            return ActionResult(success=False, message="Look at what?")

        if owner_id is not None:
            return self._look_at_worn(actor, owner_id, item_name)

        return self._look_at_contained(actor, container_id, item_name)

    def _look_at_worn(
        self,
        actor: ObjectDB,
        owner_id: int,
        item_name: str,
    ) -> ActionResult:
        from world.items.services.appearance import (  # noqa: PLC0415
            visible_worn_items_for,
        )

        try:
            owner = ObjectDB.objects.get(pk=owner_id)
        except ObjectDB.DoesNotExist:
            return ActionResult(success=False, message="They aren't here.")

        visible = visible_worn_items_for(owner, observer=actor)
        item = self._find_by_name(
            visible,
            item_name,
            key=lambda v: v.item_instance,
        )
        if item is None:
            return ActionResult(
                success=False,
                message=f"You don't see anything by that name on {owner.key}.",
            )

        return ActionResult(success=True, message=self._render_item(item))

    def _look_at_contained(
        self,
        actor: ObjectDB,
        container_id: int,
        item_name: str,
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from flows.object_states.item_state import ItemState  # noqa: PLC0415

        try:
            container_obj = ObjectDB.objects.get(pk=container_id)
        except ObjectDB.DoesNotExist:
            return ActionResult(success=False, message="That isn't here.")

        try:
            container_instance = container_obj.item_instance
        except ObjectDB.item_instance.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
            return ActionResult(success=False, message="That isn't a container.")

        # Reach gate: clients can POST any container pk via the action
        # dispatcher. Without this check, an actor could read the contents
        # of any open container in the database. Staff bypass mirrors the
        # rest of the look pipeline (concealed worn items, etc.).
        if not is_staff_observer(actor):
            sdm = SceneDataManager()
            container_state = ItemState(container_instance, context=sdm)
            if not container_state.is_reachable_by(actor):
                return ActionResult(success=False, message="That isn't here.")

        if container_instance.template.supports_open_close and not container_instance.is_open:
            return ActionResult(success=False, message="That container is closed.")

        contents = list(container_instance.contents.all())
        item = self._find_by_name(contents, item_name)
        if item is None:
            container_label = container_instance.display_name
            return ActionResult(
                success=False,
                message=(f"You don't see anything by that name in the {container_label}."),
            )

        return ActionResult(success=True, message=self._render_item(item))

    @staticmethod
    def _find_by_name(
        items: list[Any],
        name: str,
        key: Callable[[Any], ItemInstance] = lambda x: x,
    ) -> ItemInstance | None:
        """Case-insensitive search by display_name. Returns None on miss."""
        target = name.lower().strip()
        for entry in items:
            instance = key(entry)
            if instance.display_name.lower() == target:
                return instance
        # Substring fallback
        for entry in items:
            instance = key(entry)
            if target in instance.display_name.lower():
                return instance
        return None

    @staticmethod
    def _render_item(item: ItemInstance) -> str:
        """Format the item appearance for the look output."""
        return f"{item.display_name}\n{item.display_description}"


@dataclass
class InventoryAction(Action):
    """View the character's inventory."""

    key: str = "inventory"
    name: str = "Inventory"
    icon: str = "backpack"
    category: str = "perception"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        items = caller_state.contents
        if not items:
            return ActionResult(success=True, message="You are not carrying anything.")

        names = [it.get_display_name(looker=caller_state) for it in items]
        text = "You are carrying: " + ", ".join(names)
        return ActionResult(success=True, message=text)
