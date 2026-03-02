"""Movement-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_room_state
from flows.service_functions.movement import check_exit_traversal, move_object, traverse_exit

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class GetAction(Action):
    """Pick up an item."""

    key: str = "get"
    name: str = "Get"
    icon: str = "hand"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_get"
    result_event: str | None = "get"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Get what?")

        sdm = context.scene_data if context else SceneDataManager()
        item_state = sdm.initialize_state_for_object(target)
        actor_state = sdm.initialize_state_for_object(actor)

        move_object(item_state, actor_state)

        message_location(
            actor_state,
            "$You() $conj(pick) up {target}.",
            mapping={"target": item_state},
        )

        return ActionResult(success=True)


@dataclass
class DropAction(Action):
    """Drop an item."""

    key: str = "drop"
    name: str = "Drop"
    icon: str = "drop"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_drop"
    result_event: str | None = "drop"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Drop what?")

        if actor.location is None:
            return ActionResult(success=False, message="You have nowhere to drop that.")

        sdm = context.scene_data if context else SceneDataManager()
        item_state = sdm.initialize_state_for_object(target)
        location_state = sdm.initialize_state_for_object(actor.location)

        move_object(item_state, location_state)

        actor_state = sdm.initialize_state_for_object(actor)

        message_location(
            actor_state,
            "$You() $conj(drop) {target}.",
            mapping={"target": item_state},
        )

        return ActionResult(success=True)


@dataclass
class GiveAction(Action):
    """Give an item to another character."""

    key: str = "give"
    name: str = "Give"
    icon: str = "gift"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_give"
    result_event: str | None = "give"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        recipient = kwargs.get("recipient")
        if target is None or recipient is None:
            return ActionResult(success=False, message="Give what to whom?")

        sdm = context.scene_data if context else SceneDataManager()
        item_state = sdm.initialize_state_for_object(target)
        recipient_state = sdm.initialize_state_for_object(recipient)

        move_object(item_state, recipient_state)

        actor_state = sdm.initialize_state_for_object(actor)

        message_location(
            actor_state,
            "$You() $conj(give) {target} to {recipient}.",
            target=recipient_state,
            mapping={
                "target": item_state,
                "recipient": recipient_state,
            },
        )

        return ActionResult(success=True)


@dataclass
class TraverseExitAction(Action):
    """Move through an exit."""

    key: str = "traverse_exit"
    name: str = "Go"
    icon: str = "door"
    category: str = "movement"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_traverse"
    result_event: str | None = "traverse"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Go where?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        exit_state = sdm.initialize_state_for_object(target)

        check_exit_traversal(caller_state, exit_state)

        destination = target.destination
        dest_state = sdm.initialize_state_for_object(destination)
        traverse_exit(caller_state, exit_state, dest_state)

        # Re-initialize caller state for new location and send room state
        caller_state = sdm.initialize_state_for_object(actor)
        send_room_state(caller_state)

        return ActionResult(success=True)


@dataclass
class HomeAction(Action):
    """Return to home location."""

    key: str = "home"
    name: str = "Home"
    icon: str = "home"
    category: str = "movement"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        home = actor.home
        if home is None:
            return ActionResult(success=False, message="You have no home set.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        home_state = sdm.initialize_state_for_object(home)

        move_object(actor_state, home_state, quiet=False)

        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True)
