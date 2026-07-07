"""Positioning-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import StaffOnlyPrerequisite
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import send_room_state
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import Position, PositionBlueprint
from world.areas.positioning.services import instantiate_blueprint, move_to_position, take_position


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
