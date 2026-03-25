from __future__ import annotations

from typing import Any, cast

from world.scenes.constants import SceneAction
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.scenes.models import Scene

ActionType = SceneAction


def broadcast_scene_message(scene: Scene, action: ActionType) -> None:
    """Send scene information to all accounts in the scene's location.

    The room caches its active scene when a scene starts or ends so that
    subsequent room state payloads can avoid extra database lookups.

    Args:
        scene: Scene to announce.
        action: Event type for the scene.
    """
    location = scene.location
    if location is None:
        return
    if action in (SceneAction.START, SceneAction.END):
        invalidate_active_scene_cache(location)
        cast(Any, location).active_scene = scene if action == SceneAction.START else None
    for obj in location.contents:
        try:
            account = obj.account
        except AttributeError:
            continue
        is_owner = scene.is_owner(account)
        payload = {
            "action": action,
            "scene": {
                "id": scene.id,
                "name": scene.name,
                "description": scene.description,
                "is_owner": is_owner,
            },
        }
        account.msg(scene=((), payload))
