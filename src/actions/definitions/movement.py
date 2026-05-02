"""Movement-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.definitions.item_helpers import resolve_item_instance
from actions.types import ActionContext, ActionResult, TargetType
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_room_state
from flows.service_functions.inventory import drop, give, pick_up
from flows.service_functions.movement import check_exit_traversal, move_object, traverse_exit
from world.items.exceptions import InventoryError
from world.mechanics.constants import ChallengeType
from world.mechanics.models import ChallengeInstance


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

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Get what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be picked up.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            pick_up(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

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

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Drop what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be dropped.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            drop(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

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

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target", "recipient"})

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

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be given.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        recipient_state = sdm.initialize_state_for_object(recipient)
        item_state = ItemState(item_instance, context=sdm)

        try:
            give(actor_state, recipient_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

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

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Go where?")

        # Check for active challenges blocking this exit
        blocking_challenges = ChallengeInstance.objects.filter(
            location=target,
            is_active=True,
            is_revealed=True,
            template__challenge_type=ChallengeType.INHIBITOR,
        ).select_related("template")

        if blocking_challenges.exists():
            challenge_data = [
                {
                    "id": ci.pk,
                    "name": ci.template.name,
                    "description": ci.template.description_template,
                }
                for ci in blocking_challenges
            ]
            return ActionResult(
                success=False,
                message="The way is blocked.",
                data={"challenges": challenge_data},
            )

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
