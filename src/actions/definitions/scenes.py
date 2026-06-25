"""Scene lifecycle actions: start/finish a scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

# Re-use the same NOT_IN_A_ROOM_MESSAGE constant (defined in rounds.py and checked here).
NOT_IN_A_ROOM_MESSAGE = "You are not in a room."

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Scene


def _active_scene_for_room(room: ObjectDB) -> Scene | None:
    """Return the active Scene for a room, or None."""
    from world.scenes.models import Scene as SceneModel  # noqa: PLC0415

    return SceneModel.objects.filter(location=room, is_active=True).first()


@dataclass
class StartSceneAction(Action):
    """Start a scene in the actor's current room.

    If no active scene exists, creates one and grants co-ownership to every
    present PC with a controlling account.  If a scene is already active, the
    actor is recorded as a (non-owner) participant and informed.  Ungated.
    """

    key: str = "start_scene"
    name: str = "Start Scene"
    icon: str = "play"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.place_services import ensure_scene_for_location  # noqa: PLC0415
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            add_present_as_co_owners,
            resolve_actor_account,
        )

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            scene = ensure_scene_for_location(room)
            add_present_as_co_owners(scene, room)
            return ActionResult(success=True, message="A scene begins.")

        # Scene already exists — join the actor as a non-owner participant.
        account = resolve_actor_account(actor)
        if account is not None:
            from world.scenes.models import SceneParticipation  # noqa: PLC0415

            SceneParticipation.objects.get_or_create(
                scene=scene,
                account=account,
                defaults={"is_owner": False},
            )
        return ActionResult(success=True, message="A scene is already active here.")


@dataclass
class FinishSceneAction(Action):
    """Finish the active scene in the actor's current room.

    Gated: only the scene's GM, a co-owner, or a staff account may finish the
    scene.  Delegates to ``finish_scene_full`` for the full orchestration.
    """

    key: str = "finish_scene"
    name: str = "Finish Scene"
    icon: str = "stop-circle"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            actor_can_administer_scene,
            finish_scene_full,
            resolve_actor_account,
        )

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        if not actor_can_administer_scene(actor, scene):
            return ActionResult(
                success=False,
                message="Only the scene's GM or an owner can finish the scene.",
            )

        finish_scene_full(scene, by_account=resolve_actor_account(actor))
        return ActionResult(success=True, message="The scene comes to a close.")
