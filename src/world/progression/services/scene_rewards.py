"""
Service functions for scene completion side effects.

Before #3738 a finished scene also paid each participant a bonus weekly vote;
nominations have no budget, so the only remaining step is settling the
scene's reaction windows.
"""

from world.scenes.models import Scene


def on_scene_finished(scene: Scene) -> None:
    """Settle a finished scene's reaction windows.

    Closes every open reaction window (#904), firing per-kind settlement hooks.

    Args:
        scene: The scene that just finished.
    """
    from world.scenes.reaction_services import settle_windows_for_scene

    settle_windows_for_scene(scene)
