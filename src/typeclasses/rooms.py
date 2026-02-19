"""
Room

Rooms are simple containers that has no location of their own.

"""

from functools import cached_property

from evennia.objects.objects import DefaultRoom

from evennia_extensions.models import RoomProfile
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

    def at_object_creation(self):
        """Called once when the room is first created via Evennia."""
        super().at_object_creation()
        RoomProfile.objects.get_or_create(objectdb=self)

    @cached_property
    def item_data(self):
        """Room-specific item data handler."""
        from evennia_extensions.data_handlers import RoomItemDataHandler

        return RoomItemDataHandler(self)

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

    @property
    def sentient_contents(self) -> list:
        """Return objects in this room that have active sessions."""
        sentients = []
        for obj in self.contents:
            try:
                if obj.sessions.all():
                    sentients.append(obj)
            except AttributeError:
                continue
        return sentients

    def _broadcast_room_state(self, exclude=None) -> None:
        """Send ``room_state`` updates to room occupants.

        Args:
            exclude: Object to omit from notifications.
        """
        room_state = self.scene_state
        if room_state is None:
            return
        for obj in self.sentient_contents:
            if obj is exclude:
                continue
            if hasattr(obj, "send_room_state"):
                obj.send_room_state()

    def at_object_receive(self, obj, source_location, **kwargs):
        """Notify occupants when an object enters.

        Args:
            obj: Object entering the room.
            source_location: Where the object came from.
            **kwargs: Arbitrary keyword arguments.
        """
        super().at_object_receive(obj, source_location, **kwargs)
        self._broadcast_room_state(exclude=obj)

    def at_object_leave(self, obj, target_location, **kwargs):
        """Notify occupants when an object leaves.

        Args:
            obj: Object leaving the room.
            target_location: Destination of the object.
            **kwargs: Arbitrary keyword arguments.
        """
        super().at_object_leave(obj, target_location, **kwargs)
        self._broadcast_room_state(exclude=obj)
