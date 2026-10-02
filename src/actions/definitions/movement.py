"""Movement-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
import uuid

from evennia.objects.models import ObjectDB
from evennia.utils import delay

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.item_helpers import (
    MENU_TARGET_KEY,
    emit_typed_item_intent,
    resolve_item_instance,
    resolve_typed_item,
)
from actions.prerequisites import Prerequisite
from actions.target_menu_types import MenuTargetKind
from actions.target_resolution import resolve_persona_pk_to_character
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from evennia_extensions.models import room_is_publicly_listed
from flows.events.payloads import ActionIntentPayload
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_room_state
from flows.service_functions.inventory import (
    drop,
    give,
    pick_up,
    validate_drop,
    validate_give,
    validate_pick_up,
)
from flows.service_functions.movement import check_exit_traversal, move_object, traverse_exit
from world.areas.positioning.travel import find_route
from world.conditions.services import can_perceive
from world.items.exceptions import InventoryError, NotReachable
from world.mechanics.constants import ChallengeType
from world.mechanics.models import ChallengeInstance
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet

_GET_DROP_KINDS = frozenset({MenuTargetKind.ITEMS, MenuTargetKind.OBJECTS})
_GET_DROP_UNAVAILABLE = "That isn't available."
_KWARGS_KEY = "kwargs"
_MOVEMENT_TARGET_KEY = "target"


def _movement_item(actor, kwargs):
    if MENU_TARGET_KEY in kwargs:
        resolved = resolve_typed_item(actor, kwargs, allowed_kinds=_GET_DROP_KINDS)
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("target"))


@dataclass
class _ItemMovementPrerequisite(Prerequisite):
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        context = context or {}
        kwargs = dict(context.get(_KWARGS_KEY, {}))
        if MENU_TARGET_KEY not in kwargs and _MOVEMENT_TARGET_KEY not in kwargs:
            kwargs[_MOVEMENT_TARGET_KEY] = target
        item = _movement_item(actor, kwargs)
        if MENU_TARGET_KEY in kwargs:
            if item is None or not self.action.is_applicable(actor, kwargs=kwargs):
                return False, _GET_DROP_UNAVAILABLE
        elif kwargs.get("target") is None:
            return False, self.action.missing_target_message
        elif item is None:
            return False, self.action.invalid_target_message
        sdm = context.get("scene_data")
        sdm = sdm if sdm is not None else SceneDataManager()
        try:
            self.action.validate(CharacterState(actor, context=sdm), ItemState(item, context=sdm))
        except InventoryError as exc:
            return False, exc.user_message
        return True, ""


class _ItemMovementAction(Action):
    """Share target lifecycle adaptation for Get and Drop."""

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), _ItemMovementPrerequisite(action=self)]

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        return emit_typed_item_intent(
            context,
            actor,
            super()._emit_intent,
            allowed_kinds=_GET_DROP_KINDS,
        )


@dataclass
class GetAction(_ItemMovementAction):
    """Pick up an item, retaining servant retrieval on failed reach."""

    missing_target_message: ClassVar[str] = "Get what?"
    invalid_target_message: ClassVar[str] = "That can't be picked up."

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _movement_item(actor, kwargs)
        if item is None or item.game_object is None or item.contained_in is not None:
            return False
        if actor.location is None or item.game_object.location != actor.location:
            return False
        sheet = actor.character_sheet
        return sheet is None or item.holder_character_sheet_id != sheet.pk

    @staticmethod
    def validate(character: CharacterState, item: ItemState) -> None:
        try:
            validate_pick_up(character, item)
        except NotReachable:
            from world.npc_services.servant_fetch import can_servant_fetch  # noqa: PLC0415

            if not can_servant_fetch(actor=character.obj, item_instance=item.instance):
                raise

    key: str = "get"
    name: str = "Get"
    icon: str = "hand"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_instance = _movement_item(actor, kwargs)
        if MENU_TARGET_KEY in kwargs:
            if item_instance is None or not self.is_applicable(actor, kwargs=kwargs):
                return ActionResult(success=False, message=_GET_DROP_UNAVAILABLE)
        elif kwargs.get("target") is None:
            return ActionResult(success=False, message=self.missing_target_message)
        elif item_instance is None:
            return ActionResult(success=False, message=self.invalid_target_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)

        try:
            pick_up(actor_state, item_state)
        except NotReachable:
            from world.npc_services.servant_fetch import (  # noqa: PLC0415
                can_servant_fetch,
                servant_fetch_item,
            )

            if can_servant_fetch(actor=actor, item_instance=item_instance):
                servant_fetch_item(actor=actor, item_instance=item_instance)
                return ActionResult(
                    success=True, message="A servant bows and departs to fetch that."
                )
            return ActionResult(success=False, message=NotReachable.user_message)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(pick) up {target}.",
            mapping={"target": item_instance.display_name},
        )

        return ActionResult(success=True)


@dataclass
class DropAction(_ItemMovementAction):
    """Drop physically possessed items, including worn equipment."""

    missing_target_message: ClassVar[str] = "Drop what?"
    invalid_target_message: ClassVar[str] = "That can't be dropped."
    validate = staticmethod(validate_drop)

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _movement_item(actor, kwargs)
        return (
            item is not None
            and item.game_object is not None
            and ItemState(item, context=SceneDataManager()).is_in_possession(actor)
        )

    key: str = "drop"
    name: str = "Drop"
    icon: str = "drop"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_instance = _movement_item(actor, kwargs)
        if MENU_TARGET_KEY in kwargs:
            if item_instance is None or not self.is_applicable(actor, kwargs=kwargs):
                return ActionResult(success=False, message=_GET_DROP_UNAVAILABLE)
        elif kwargs.get("target") is None:
            return ActionResult(success=False, message=self.missing_target_message)
        elif item_instance is None:
            return ActionResult(success=False, message=self.invalid_target_message)

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
            mapping={"target": item_instance.display_name},
        )

        return ActionResult(success=True)


_GIVE_UNAVAILABLE = "That isn't available."
_GIVE_RECIPIENT = "recipient_persona_id"
_GIVE_LEGACY_RECIPIENTS = frozenset({"recipient", "recipient_id"})


@dataclass
class _GiveIntentPayload(ActionIntentPayload):
    """Typed Give intent exposes its authored public-persona recipient choice."""

    recipient_persona_id: Any = None


def _give_item(actor: ObjectDB, kwargs: dict[str, Any]):
    if MENU_TARGET_KEY in kwargs:
        if _GIVE_LEGACY_RECIPIENTS.intersection(kwargs):
            return None
        resolved = resolve_typed_item(actor, kwargs)
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("target"))


def _give_recipient(actor: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    if MENU_TARGET_KEY not in kwargs:
        value = kwargs.get("recipient")
        return value if isinstance(value, ObjectDB) else None
    if _GIVE_LEGACY_RECIPIENTS.intersection(kwargs):
        return None
    value = kwargs.get(_GIVE_RECIPIENT)
    if type(value) is not int or value <= 0:
        return None
    persona = Persona.objects.filter(pk=value).first()
    if persona is None:
        return None
    recipient = resolve_persona_pk_to_character(value)
    if recipient is None or recipient == actor:
        return None
    if actor.location is None or recipient.location != actor.location:
        return None
    if active_persona_for_sheet(persona.character_sheet) != persona:
        return None
    return recipient if can_perceive(actor, recipient) else None


@dataclass
class _GiveItemPrerequisite(Prerequisite):
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        kwargs = (context or {}).get("kwargs", {})
        if MENU_TARGET_KEY in kwargs and not self.action.is_applicable(actor, kwargs=kwargs):
            return False, _GIVE_UNAVAILABLE
        return True, ""


@dataclass
class _GiveRecipientPrerequisite(Prerequisite):
    required_input_names: ClassVar[frozenset[str]] = frozenset({_GIVE_RECIPIENT})
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        context = context or {}
        kwargs = dict(context.get("kwargs", {}))
        if MENU_TARGET_KEY not in kwargs and _MOVEMENT_TARGET_KEY not in kwargs:
            kwargs[_MOVEMENT_TARGET_KEY] = target
        # Report bound typed failures once, in the preceding prerequisite.
        if MENU_TARGET_KEY in kwargs and not self.action.is_applicable(actor, kwargs=kwargs):
            return True, ""
        if MENU_TARGET_KEY not in kwargs and (
            kwargs.get("target") is None or kwargs.get("recipient") is None
        ):
            return False, "Give what to whom?"
        item = _give_item(actor, kwargs)
        recipient = _give_recipient(actor, kwargs)
        if item is None:
            return False, _GIVE_UNAVAILABLE if MENU_TARGET_KEY in kwargs else "That can't be given."
        if recipient is None:
            return False, _GIVE_UNAVAILABLE
        sdm = context.get("scene_data")
        sdm = sdm if sdm is not None else SceneDataManager()
        try:
            validate_give(
                CharacterState(actor, context=sdm),
                CharacterState(recipient, context=sdm),
                ItemState(item, context=sdm),
            )
        except InventoryError as exc:
            return False, exc.user_message
        return True, ""


@dataclass
class GiveAction(Action):
    """Give a physical item, with a declared public-persona recipient choice."""

    key: str = "give"
    name: str = "Give"
    icon: str = "gift"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target", "recipient"})
    required_input_names: ClassVar[frozenset[str]] = frozenset({_GIVE_RECIPIENT})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [
            *super().get_prerequisites(),
            _GiveItemPrerequisite(action=self),
            _GiveRecipientPrerequisite(action=self),
        ]

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _give_item(actor, kwargs)
        return (
            item is not None
            and item.game_object is not None
            and ItemState(item, context=SceneDataManager()).is_in_possession(actor)
        )

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        if actor is None or MENU_TARGET_KEY not in context.kwargs:
            return super()._emit_intent(context, actor)

        def emit_give_intent(bound_context: ActionContext, bound_actor: ObjectDB | None):
            from flows.constants import EventName  # noqa: PLC0415
            from flows.emit import emit_event  # noqa: PLC0415

            original_target = bound_context.kwargs.get("target")
            intent = _GiveIntentPayload(
                actor=bound_actor,
                action_key=self.key,
                target=original_target,
                recipient_persona_id=bound_context.kwargs.get(_GIVE_RECIPIENT),
            )
            stack = emit_event(EventName.ACTION_INTENT, intent, location=bound_actor.location)
            if stack.was_cancelled():
                return ActionResult(
                    success=False, message=intent.cancel_message or "Something prevents you."
                )
            if intent.target is not original_target:
                bound_context.kwargs["target"] = intent.target
            # Invalid rewrites must refuse, not fall back to the selected person.
            bound_context.kwargs[_GIVE_RECIPIENT] = intent.recipient_persona_id
            return None

        return emit_typed_item_intent(context, actor, emit_give_intent)

    def recipient_candidates(
        self, actor: ObjectDB, *, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        """Read current public recipients with this action's complete availability."""
        if MENU_TARGET_KEY not in kwargs or not self.is_applicable(actor, kwargs=kwargs):
            return ()
        if actor.location is None:
            return ()
        rows = []
        for persona in Persona.objects.filter(
            character_sheet__character__db_location=actor.location
        ).order_by("pk"):
            candidate_kwargs = {**kwargs, _GIVE_RECIPIENT: persona.pk}
            if _give_recipient(actor, candidate_kwargs) is None:
                continue
            checked = self.check_availability(
                actor, context={"kwargs": candidate_kwargs}, pending_inputs=frozenset()
            )
            rows.append(
                {
                    "recipient_persona_id": persona.pk,
                    "name": persona.display_ic(),
                    "available": checked.available,
                    "reasons": list(checked.reasons),
                }
            )
        return tuple(rows)

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        typed = MENU_TARGET_KEY in kwargs
        if typed and not self.is_applicable(actor, kwargs=kwargs):
            return ActionResult(success=False, message=_GIVE_UNAVAILABLE)
        if not typed and (kwargs.get("target") is None or kwargs.get("recipient") is None):
            return ActionResult(success=False, message="Give what to whom?")
        item_instance = _give_item(actor, kwargs)
        if item_instance is None:
            return ActionResult(
                success=False, message=_GIVE_UNAVAILABLE if typed else "That can't be given."
            )
        recipient = _give_recipient(actor, kwargs)
        if recipient is None:
            return ActionResult(success=False, message=_GIVE_UNAVAILABLE)
        sdm = context.scene_data if context else SceneDataManager()
        try:
            validate_give(
                CharacterState(actor, context=sdm),
                CharacterState(recipient, context=sdm),
                ItemState(item_instance, context=sdm),
            )
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)
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
            mapping={"target": item_instance.display_name, "recipient": recipient_state},
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
        try:
            perform_portal_travel(actor, route)
        except CommandError as exc:
            # #2989 expulsion bar — perform_portal_travel raises pre-move when
            # the destination bars the actor. Surface as a clean failure
            # rather than letting the exception propagate; the walking path
            # is not tried as a fallback (the bar applies to every route).
            return ActionResult(success=False, message=exc.msg)
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

        # #2989 expulsion bar — a barred character's home may be the room
        # they were shown out of; block the same as ordinary exit traversal
        # and portal travel rather than letting `home` bypass it.
        from world.npc_services.expulsion_services import active_bar_for  # noqa: PLC0415

        barred_sheet = actor.character_sheet
        if barred_sheet is not None and active_bar_for(home, barred_sheet) is not None:
            return ActionResult(success=False, message="You are barred from entering there.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        home_state = sdm.initialize_state_for_object(home)

        move_object(actor_state, home_state, quiet=False)

        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True)
