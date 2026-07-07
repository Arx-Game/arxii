"""Positioning-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import StaffOnlyPrerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import send_room_state
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import Position, PositionBlueprint
from world.areas.positioning.services import (
    instantiate_blueprint,
    move_to_position,
    place_in_position,
    take_position,
)


@dataclass
class MoveToPositionAction(Action):
    """Move the actor to a different Position within the same room.

    Position is NOT an ObjectDB, so this action does not use the ObjectDB
    target resolution path. The destination is passed as ``position_id``
    (an int pk) in the action kwargs. ``objectdb_target_kwargs`` is left
    empty — the inputfunc resolver would not know how to handle a Position pk.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="move_to_position"``,
    ``position_id=<Position.pk>``.

    The dispatch layer passes the ref's ``position_id`` as a kwarg; this
    action resolves it to a ``Position`` instance and delegates to
    ``services.move_to_position``.
    """

    key: str = "move_to_position"
    name: str = "Move"
    icon: str = "walking"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        position_id = kwargs.get("position_id")
        if position_id is None:
            return ActionResult(success=False, message="Move where?")

        try:
            target = Position.objects.get(pk=position_id)
        except Position.DoesNotExist:
            return ActionResult(success=False, message="That position does not exist.")

        try:
            move_to_position(actor, target)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True)


@dataclass
class TakePositionAction(Action):
    """Voluntary entry onto the position graph for an UNPLACED actor (#2005).

    Position is NOT an ObjectDB, so this action does not use the ObjectDB
    target resolution path. The destination is passed as ``position_id``
    (an int pk) in the action kwargs, mirroring ``MoveToPositionAction``.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="take_position"``,
    ``position_id=<Position.pk>``.

    The dispatch layer passes the ref's ``position_id`` as a kwarg; this
    action resolves it to a ``Position`` instance and delegates to
    ``services.take_position``. Restricted to PRIMARY/FEATURE entry-point
    kinds by the service; ELEVATED/AERIAL/etc. are unreachable this way.
    """

    key: str = "take_position"
    name: str = "Take position"
    icon: str = "map-marker"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        position_id = kwargs.get("position_id")
        if position_id is None:
            return ActionResult(success=False, message="Take position where?")

        try:
            target = Position.objects.get(pk=position_id)
        except Position.DoesNotExist:
            return ActionResult(success=False, message="That position does not exist.")

        try:
            take_position(actor, target)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True)


_ERR_NO_GM_PERMISSION = "Only staff or the scene's GM can do that."
_ERR_NO_POSITION = "Place at which position?"
_ERR_NO_TARGET = "Place which object?"
_ERR_TARGET_NOT_FOUND = "That object does not exist."
_ERR_TARGET_NOT_CO_LOCATED = "That object is not here."
_ERR_POSITION_NOT_FOUND = "That position does not exist."


def _actor_may_gm_place(actor: ObjectDB) -> bool:
    """True when *actor* is staff, or the GM of the active scene in their room.

    Mirrors ``_actor_may_gm_battle`` (``actions/definitions/battles.py``), but
    the scene is derived from the actor's current room rather than an
    existing Battle. No active scene in the room means staff-only.
    """
    from actions.definitions.scenes import _active_scene_for_room  # noqa: PLC0415

    account = resolve_account_or_none(actor)
    if account is None:
        return False
    if account.is_staff:
        return True
    room = actor.location
    if room is None:
        return False
    scene = _active_scene_for_room(room)
    return scene is not None and scene.is_gm(account)


def _resolve_gm_place_target(
    actor: ObjectDB, target_object_id: int, position_id: int
) -> tuple[ObjectDB, Position] | ActionResult:
    """Resolve + validate the (target, position) pair for GM placement.

    Returns an error ``ActionResult`` when the target doesn't exist, isn't
    co-located with *actor*, or the position doesn't exist.
    """
    try:
        target = ObjectDB.objects.get(pk=target_object_id)
    except ObjectDB.DoesNotExist:
        return ActionResult(success=False, message=_ERR_TARGET_NOT_FOUND)
    if target.db_location_id != actor.db_location_id:
        return ActionResult(success=False, message=_ERR_TARGET_NOT_CO_LOCATED)
    try:
        position = Position.objects.get(pk=position_id)
    except Position.DoesNotExist:
        return ActionResult(success=False, message=_ERR_POSITION_NOT_FOUND)
    return target, position


@dataclass
class GMPlaceInPositionAction(Action):
    """GM/staff unchecked placement of a co-located object (#2005).

    Wraps ``place_in_position`` — the UNCHECKED primitive that bypasses
    entry-kind and mobility validation by design. This is the staging /
    staff-teleport counterpart to the validated ``TakePositionAction``.

    Gate: staff OR the GM of the active scene in the actor's current room
    (mirrors ``_actor_may_gm_battle``). No active scene means staff-only.
    Deliberately does NOT use ``StaffOnlyPrerequisite`` — placement is a
    GM verb, not a staff-exclusive one.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="gm_place_in_position"``,
    ``position_id=<Position.pk>``, ``target_object_id=<ObjectDB.pk>``.

    ``target_object_id`` must resolve to an ObjectDB co-located with the
    actor (same ``db_location``); this action does not use the ObjectDB
    target-resolution path (``target_type=SELF``, mirroring
    ``MoveToPositionAction``/``TakePositionAction``), since ``position_id``
    also needs manual resolution.
    """

    key: str = "gm_place_in_position"
    name: str = "Place in Position"
    icon: str = "crosshairs"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        if not _actor_may_gm_place(actor):
            return ActionResult(success=False, message=_ERR_NO_GM_PERMISSION)

        position_id = kwargs.get("position_id")
        if position_id is None:
            return ActionResult(success=False, message=_ERR_NO_POSITION)

        target_object_id = kwargs.get("target_object_id")
        if target_object_id is None:
            return ActionResult(success=False, message=_ERR_NO_TARGET)

        resolved = _resolve_gm_place_target(actor, target_object_id, position_id)
        if isinstance(resolved, ActionResult):
            return resolved
        target, position = resolved

        try:
            place_in_position(target, position)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        target_state = sdm.initialize_state_for_object(target)
        send_room_state(target_state)

        return ActionResult(success=True)


@dataclass
class SetTheStageAction(Action):
    """Staff-only action: instantiate a PositionBlueprint into the actor's current room.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="set_the_stage"``,
    ``blueprint_id=<PositionBlueprint.pk>``, optional ``replace`` kwarg (bool).

    The dispatch layer passes ``ref.blueprint_id`` as a kwarg; this action
    resolves it to a ``PositionBlueprint`` instance and delegates to
    ``services.instantiate_blueprint``.
    """

    key: str = "set_the_stage"
    name: str = "Set the Stage"
    icon: str = "map"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [StaffOnlyPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        blueprint_id = kwargs.get("blueprint_id")
        if blueprint_id is None:
            return ActionResult(success=False, message="Set the stage with which blueprint?")

        try:
            blueprint = PositionBlueprint.objects.get(pk=blueprint_id)
        except PositionBlueprint.DoesNotExist:
            return ActionResult(success=False, message="That blueprint does not exist.")

        replace = bool(kwargs.get("replace", False))

        try:
            instantiate_blueprint(blueprint, actor.location, replace=replace)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True)
