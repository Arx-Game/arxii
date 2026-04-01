"""
Service functions for awarding scene completion rewards.

When a scene finishes, each participant earns +1 bonus vote for the week.
"""

from world.progression.services.voting import increment_scene_bonus
from world.scenes.models import Scene


def on_scene_finished(scene: Scene) -> None:
    """Grant scene completion rewards to all participants.

    For each SceneParticipation in the scene, increments the participant's
    weekly vote budget by 1.

    Args:
        scene: The scene that just finished.
    """
    for participation in scene.participations.select_related("account"):
        increment_scene_bonus(participation.account)
