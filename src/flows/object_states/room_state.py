from typing import TYPE_CHECKING

from flows.object_states.base_state import BaseState
from world.scenes.models import Scene

if TYPE_CHECKING:
    from flows.scene_data_manager import SceneDataManager
    from typeclasses.rooms import Room


class RoomState(BaseState):
    """
    RoomState represents the state for room objects.
    """

    def __init__(self, obj: "Room", context: "SceneDataManager"):
        """Initialize RoomState with proper Room typing."""
        super().__init__(obj, context)
        # Now mypy knows self.obj is a Room instance
        self.obj: Room

    default_description = "This is a room."

    @property
    def active_scene(self) -> Scene | None:
        """Return the active scene cached on this room."""
        return self.obj.active_scene

    @property
    def appearance_template(self) -> str:
        return "{name}\n{desc}\n{exits}\n{characters}\n{things}"

    @property
    def description(self) -> str:
        try:
            return self.obj.item_data.desc or self.default_description
        except AttributeError:
            return self.default_description

    def get_categories(self) -> dict:
        # For now, no extra room-specific categories.
        return {}

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return ``False`` to disallow moving rooms."""

        return False
