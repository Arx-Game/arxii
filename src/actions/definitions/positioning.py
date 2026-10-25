"""Positioning-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import (
    CombatMovementPrerequisite,
    MinimumGMLevelPrerequisite,
    Prerequisite,
)
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import send_room_state
from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import Position, PositionBlueprint
from world.areas.positioning.services import (
    edge_between,
    edge_blocks_crossing,
    enter_aerial,
    instantiate_blueprint,
    is_aerial,
    leave_aerial,
    move_to_position,
    place_in_position,
    position_of,
    take_position,
)
from world.areas.positioning.traversal import best_crossing_cost, traversals_of
from world.combat.services.held_ground import held_position_ids_against, holder_names
from world.combat.services.movement_budget import (
    active_combat_participant,
    hops_for,
    hops_left,
    spend_combat_hop,
)
from world.gm.constants import GMLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.combat.models import CombatParticipant

STOPPED_BY_HOLDER = "You are stopped by {name}."


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

    def get_prerequisites(self) -> list[Prerequisite]:
        """In a live encounter a move costs a hop and is refused outside declaration (#4607)."""
        return [CombatMovementPrerequisite()]

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
            return ActionResult(success=False, message=_ERR_POSITION_NOT_FOUND)

        traversals = traversals_of(actor)
        cost = _move_cost(actor, target, traversals)
        participant = _declaring_participant(actor)
        if participant is not None and cost > 1:
            left = hops_left(participant)
            if cost > left:
                return ActionResult(
                    success=False,
                    message=f"That crossing takes {cost} hops; you have {left} left.",
                )

        # Read before the move: a mover's own place never counts as held against her.
        held = held_position_ids_against(actor) if participant is not None else frozenset()
        try:
            move_to_position(actor, target, traversals=traversals)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        # The prerequisite let a DECLARING-round move through; it now costs its hops.
        message = None
        if participant is not None:
            spend_combat_hop(participant, cost)
            message = _stop_in_held_ground(actor, participant, target, held)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        return ActionResult(success=True, message=message)


def _stop_in_held_ground(
    actor: ObjectDB, participant: CombatParticipant, target: Position, held: frozenset[int]
) -> str | None:
    """Entering a place a ready enemy holds ends the actor's movement this round (#4663).

    Spends every hop she has left and returns "You are stopped by <enemy>.", or None when
    ``target`` is not in ``held`` (``held_position_ids_against`` read before the move).
    """
    if target.pk not in held:
        return None
    participant.hops_used = hops_for(participant.character_sheet)
    participant.save(update_fields=["hops_used"])
    return STOPPED_BY_HOLDER.format(name=holder_names(actor).get(target.pk, ""))


def _declaring_participant(actor: ObjectDB) -> CombatParticipant | None:
    """The actor's participant row while its encounter is declaring a round, else None."""
    participant = active_combat_participant(actor)
    if participant is None or participant.encounter.status != RoundStatus.DECLARING:
        return None
    return participant


def _move_cost(actor: ObjectDB, target: Position, traversals: frozenset[str]) -> int:
    """Hops the step to ``target`` costs: one, or a wall's crossing cost for a climber.

    A step ``move_to_position`` will refuse is costed at one; the refusal is its to give.
    """
    current = position_of(actor)
    edge = edge_between(current, target) if current is not None else None
    if edge is None or not edge_blocks_crossing(edge):
        return 1
    return best_crossing_cost(edge, traversals) or 1


class CanFlyPrerequisite(Prerequisite):
    """The actor holds a flight capability above its baseline, is on the ground, and has
    open sky above her (#4663). A roof closes the vertical edge to everyone (#4608)."""

    def is_met(self, actor, target=None, context=None) -> tuple[bool, str]:
        if CreatureTraversal.FLIES not in traversals_of(actor):
            return False, _ERR_CANNOT_FLY
        if is_aerial(actor):
            return False, _ERR_ALREADY_AIRBORNE
        ground = position_of(actor)
        if ground is not None and ground.is_roofed:
            return False, _ERR_MOVE_ROOFED
        return True, ""


class AirbornePrerequisite(Prerequisite):
    """The actor is in the air, over ground with no roof between (#4663, #4608)."""

    def is_met(self, actor, target=None, context=None) -> tuple[bool, str]:
        if not is_aerial(actor):
            return False, _ERR_NOT_AIRBORNE
        current = position_of(actor)
        below = current.elevation_anchor if current is not None else None
        if below is not None and below.is_roofed:
            return False, _ERR_MOVE_ROOFED
        return True, ""


def _spend_one_hop(actor: ObjectDB) -> None:
    participant = _declaring_participant(actor)
    if participant is not None:
        spend_combat_hop(participant)


@dataclass
class TakeFlightAction(Action):
    """Rise into the air above the actor's position (#4663).

    A character with a flight capability above its baseline takes off into the AERIAL
    twin of where she stands (``enter_aerial``). In a live encounter it costs one hop in
    a declaring round, as a step does.

    Dispatch convention: REGISTRY ActionRef ``registry_key="take_flight"``.
    """

    key: str = "take_flight"
    name: str = "Take flight"
    icon: str = "feather"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [CombatMovementPrerequisite(), CanFlyPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        try:
            enter_aerial(actor)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        _spend_one_hop(actor)

        sdm = context.scene_data if context else SceneDataManager()
        send_room_state(sdm.initialize_state_for_object(actor))
        return ActionResult(success=True, message="You take flight.")


@dataclass
class LandAction(Action):
    """Come down from the air onto the ground below (#4663).

    ``leave_aerial`` sets the actor down on the position she was flying over. In a live
    encounter it costs one hop in a declaring round.

    Dispatch convention: REGISTRY ActionRef ``registry_key="land"``.
    """

    key: str = "land"
    name: str = "Land"
    icon: str = "arrow-down"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [CombatMovementPrerequisite(), AirbornePrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        try:
            ground = leave_aerial(actor)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        _spend_one_hop(actor)

        sdm = context.scene_data if context else SceneDataManager()
        send_room_state(sdm.initialize_state_for_object(actor))
        return ActionResult(success=True, message=f"You land at {ground.position.name}.")


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
            return ActionResult(success=False, message=_ERR_POSITION_NOT_FOUND)

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
_ERR_CANNOT_FLY = "You cannot fly."
_ERR_MOVE_ROOFED = "A roof is in the way."
_ERR_ALREADY_AIRBORNE = "You are already in the air."
_ERR_NOT_AIRBORNE = "You are not in the air."


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
    """STARTING-tier GM action: instantiate a PositionBlueprint into the actor's current room.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="set_the_stage"``,
    ``blueprint_id=<PositionBlueprint.pk>``, optional ``replace`` kwarg (bool).

    The dispatch layer passes ``ref.blueprint_id`` as a kwarg; this action
    resolves it to a ``PositionBlueprint`` instance and delegates to
    ``services.instantiate_blueprint``.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.STARTING)`` (#2117; staff
    bypass preserved) rather than staff alone -- a position blueprint carries
    no mechanical consequence, so any approved GM may stage one.
    """

    key: str = "set_the_stage"
    name: str = "Set the Stage"
    icon: str = "map"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING)]

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
            positions = instantiate_blueprint(blueprint, actor.location, replace=replace)
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        send_room_state(actor_state)

        # Name what was staged: with data alone, telnet said nothing (#3657 tranche 15).
        names = ", ".join(position.name for position in positions) or "no positions"
        return ActionResult(
            success=True, message=f"You set the stage with {blueprint.name}: {names}."
        )
