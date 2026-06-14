"""Positioning-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import send_room_state
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import Position
from world.areas.positioning.services import move_to_position


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
