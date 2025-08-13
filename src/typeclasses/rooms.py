"""
Room

Rooms are simple containers that has no location of their own.

"""

from functools import cached_property

from evennia.objects.objects import DefaultRoom

from flows.object_states.room_state import RoomState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_registry import TriggerRegistry
from typeclasses.mixins import ObjectParent
from world.scenes.models import Scene


class Room(ObjectParent, DefaultRoom):
    """
    Rooms are like any Object, except their location is None
    (which is default). They also use basetype_setup() to
    add locks so they cannot be puppeted or picked up.
    (to change that, use at_object_creation instead)

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects.
    """

    state_class = RoomState

    @cached_property
    def trigger_registry(self) -> TriggerRegistry:
        """Return the TriggerRegistry associated with this room."""
        return TriggerRegistry()

    @cached_property
    def scene_data(self) -> SceneDataManager:
        """Return the SceneDataManager associated with this room."""
        return SceneDataManager()

    @property
    def active_scene(self) -> Scene | None:
        """Scene currently running in this room."""
        try:
            return self.ndb.active_scene
        except AttributeError:
            return None

    @active_scene.setter
    def active_scene(self, value: Scene | None) -> None:
        """Cache ``value`` as the active scene for this room."""
        self.ndb.active_scene = value
