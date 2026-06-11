"""
Service functions for awarding scene completion rewards.

When a scene finishes, each participant earns +1 bonus vote for the week.
"""

from world.progression.services.voting import increment_scene_bonus
from world.scenes.models import Scene


def on_scene_finished(scene: Scene) -> None:
    """Grant scene completion rewards and settle reaction windows.

    For each SceneParticipation in the scene, increments the participant's
    weekly vote budget by 1. Then closes every open reaction window (#904),
    firing per-kind settlement hooks.

    Args:
        scene: The scene that just finished.
    """
    from world.scenes.reaction_services import settle_windows_for_scene

    for participation in scene.participations.select_related("account"):
        increment_scene_bonus(participation.account)
    settle_windows_for_scene(scene)
