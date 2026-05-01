"""Item-specific actions: equip, unequip, put_in, take_out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.definitions.item_helpers import resolve_item_instance
from actions.types import ActionContext, ActionResult, TargetType
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from flows.service_functions.inventory import equip, put_in, take_out, unequip
from world.items.exceptions import InventoryError


@dataclass
class EquipAction(Action):
    """Equip an item the character is carrying."""

    key: str = "equip"
    name: str = "Equip"
    icon: str = "shirt"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_equip"
    result_event: str | None = "equip"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Equip what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be equipped.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            equip(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(equip) {target}.",
            mapping={"target": item_state},
        )

        return ActionResult(success=True)


@dataclass
class UnequipAction(Action):
    """Remove an equipped item."""

    key: str = "unequip"
    name: str = "Unequip"
    icon: str = "shirt-off"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_unequip"
    result_event: str | None = "unequip"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Remove what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be removed.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            unequip(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(remove) {target}.",
            mapping={"target": item_state},
        )

        return ActionResult(success=True)


@dataclass
class PutInAction(Action):
    """Place an item into a container."""

    key: str = "put_in"
    name: str = "Put In"
    icon: str = "box"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_put_in"
    result_event: str | None = "put_in"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target", "container"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        container = kwargs.get("container")
        if target is None or container is None:
            return ActionResult(success=False, message="Put what into what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be put away.")

        container_instance = resolve_item_instance(container)
        if container_instance is None:
            return ActionResult(success=False, message="That isn't a container.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)
        container_state = ItemState(container_instance, context=sdm)

        try:
            put_in(actor_state, item_state, container_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(put) {target} into {container}.",
            mapping={
                "target": item_state,
                "container": container_state,
            },
        )

        return ActionResult(success=True)


@dataclass
class TakeOutAction(Action):
    """Remove an item from its container into the character's possession."""

    key: str = "take_out"
    name: str = "Take Out"
    icon: str = "box-open"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_take_out"
    result_event: str | None = "take_out"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Take what out?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be taken out.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            take_out(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(take) {target} out.",
            mapping={"target": item_state},
        )

        return ActionResult(success=True)
