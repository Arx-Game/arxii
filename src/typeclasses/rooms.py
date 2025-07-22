"""
Room

Rooms are simple containers that has no location of their own.

"""

from django.utils.functional import cached_property
from evennia.objects.objects import DefaultRoom

from flows.trigger_registry import TriggerRegistry
from typeclasses.mixins import ObjectParent


class Room(ObjectParent, DefaultRoom):
    """
    Rooms are like any Object, except their location is None
    (which is default). They also use basetype_setup() to
    add locks so they cannot be puppeted or picked up.
    (to change that, use at_object_creation instead)

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects.
    """

    @cached_property
    def trigger_registry(self) -> TriggerRegistry:
        """Return the TriggerRegistry associated with this room."""
        return TriggerRegistry()
