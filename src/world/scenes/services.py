from __future__ import annotations

from typing import Literal

from web import message_dispatcher
from world.scenes.models import Scene

ActionType = Literal["start", "update", "end"]


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
    if action == "start":
        location.active_scene = scene
    elif action == "end":
        location.active_scene = None
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
        message_dispatcher.send(account, payload=payload, payload_key="scene")
