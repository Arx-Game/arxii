"""Movement-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
import uuid

from evennia.objects.models import ObjectDB
from evennia.utils import delay

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.item_helpers import resolve_item_instance
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from evennia_extensions.models import room_is_publicly_listed
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_room_state
from flows.service_functions.inventory import drop, give, pick_up
from flows.service_functions.movement import check_exit_traversal, move_object, traverse_exit
from world.areas.positioning.travel import find_route
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
    action_category: ActionCategory = ActionCategory.PHYSICAL
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
    action_category: ActionCategory = ActionCategory.PHYSICAL
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
    action_category: ActionCategory = ActionCategory.PHYSICAL
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
    action_category: ActionCategory = ActionCategory.PHYSICAL
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
class TravelAction(Action):
    """Walk a computed route to a destination room, one hop per tick.

    Server-paced via evennia.utils.delay() — each scheduled hop reuses the
    same check_exit_traversal/traverse_exit primitives TraverseExitAction
    uses, so room-state broadcasts happen exactly as they do for a manual
    walk. A per-caller `.ndb.active_travel_token` makes cancellation and
    re-dispatch safe: every scheduled callback checks its token against the
    caller's *current* active token before acting, so a stale callback from
    a superseded or stopped walk silently no-ops instead of moving the
    player unexpectedly (#2163).
    """

    key: str = "travel_to"
    name: str = "Travel"
    icon: str = "route"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    # Tells the dispatch layer to resolve kwargs["target"] from a raw id
    # into an ObjectDB before execute() runs — same declaration
    # TraverseExitAction uses (actions/definitions/movement.py existing
    # code). Without this, a web dispatch's kwargs={"target": <room_id>}
    # would arrive at execute() as a bare int, not a Room ObjectDB.
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    # Seconds paused between each hop of the auto-walk.
    hop_delay_seconds: ClassVar[float] = 1.5

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        destination = kwargs.get("target")
        if isinstance(destination, int):
            destination = ObjectDB.objects.filter(pk=destination).first()
        if destination is None:
            return ActionResult(success=False, message="Travel where?")

        origin = actor.location
        if origin is None:
            return ActionResult(success=False, message="You have no location to travel from.")

        portal_result = self._try_portal_travel(actor, destination)
        if portal_result is not None:
            return portal_result

        route = find_route(origin, destination)
        if route is None:
            return ActionResult(success=False, message="There's no clear public path there.")
        if not route:
            return ActionResult(success=False, message="You're already there.")

        token = uuid.uuid4()
        actor.ndb.active_travel_token = token
        task = delay(
            self.hop_delay_seconds,
            self._do_hop,
            actor,
            route,
            0,
            token,
        )
        actor.ndb.active_travel_task = task

        return ActionResult(success=True, message="You set off.")

    @staticmethod
    def _try_portal_travel(actor: ObjectDB, destination: ObjectDB) -> ActionResult | None:
        """Portal branch (#2222): instant relocation when an eligible route exists.

        Tried FIRST, before the walking pathfinder — a character with a known
        portal-travel technique and anchors at both ends skips hop pacing and
        `find_route` entirely. Returns ``None`` (not a failure result) when
        ineligible, so `execute()` falls through to the walking path
        byte-identical to before this issue.
        """
        from world.magic.services.portal_travel import (  # noqa: PLC0415
            perform_portal_travel,
            portal_route,
        )

        route = portal_route(actor, destination)
        if route is None:
            return None
        perform_portal_travel(actor, route)
        return ActionResult(success=True, message="You travel instantly through the network.")

    @staticmethod
    def _do_hop(actor: ObjectDB, route: list[ObjectDB], hop_index: int, token: uuid.UUID) -> None:
        """Execute one hop of a scheduled walk, or no-op if superseded/stopped."""
        if actor.ndb.active_travel_token != token:
            return  # Superseded by a re-dispatch, or stopped — stale callback.

        exit_obj = route[hop_index]
        sdm = SceneDataManager()
        try:
            caller_state = sdm.initialize_state_for_object(actor)
            exit_state = sdm.initialize_state_for_object(exit_obj)
            check_exit_traversal(caller_state, exit_state)

            destination_room = exit_obj.destination
            if destination_room is None or not room_is_publicly_listed(destination_room):
                closed_msg = "That path is no longer open."
                raise CommandError(closed_msg)

            dest_state = sdm.initialize_state_for_object(destination_room)
            traverse_exit(caller_state, exit_state, dest_state)

            caller_state = sdm.initialize_state_for_object(actor)
            send_room_state(caller_state)
        except CommandError as err:
            actor.ndb.active_travel_token = None
            actor.ndb.active_travel_task = None
            actor.msg(f"Your route stops here: {err}")
            return
        except Exception:
            actor.ndb.active_travel_token = None
            actor.ndb.active_travel_task = None
            raise

        next_index = hop_index + 1
        if next_index >= len(route):
            actor.ndb.active_travel_token = None
            actor.ndb.active_travel_task = None
            actor.msg("You arrive.")
            return

        task = delay(
            TravelAction.hop_delay_seconds,
            TravelAction._do_hop,
            actor,
            route,
            next_index,
            token,
        )
        actor.ndb.active_travel_task = task


@dataclass
class StopTravelAction(Action):
    """Stop an in-progress travel_to walk, if one is active."""

    key: str = "stop_travel"
    name: str = "Stop Traveling"
    icon: str = "stop"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        if actor.ndb.active_travel_token is None:
            return ActionResult(success=False, message="You aren't traveling anywhere.")

        task = actor.ndb.active_travel_task
        if task is not None:
            task.cancel()

        actor.ndb.active_travel_token = None
        actor.ndb.active_travel_task = None
        return ActionResult(success=True, message="You stop where you are.")


@dataclass
class HomeAction(Action):
    """Return to home location."""

    key: str = "home"
    name: str = "Home"
    icon: str = "home"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
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
