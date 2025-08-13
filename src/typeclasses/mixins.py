from typing import TYPE_CHECKING, Self, Union

from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_registry import TriggerRegistry

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class ObjectParent:
    """
    This is a mixin that can be used to override *all* entities inheriting at
    some distance from DefaultObject (Objects, Exits, Characters and Rooms).

    Just add any method that exists on `DefaultObject` to this class. If one
    of the derived classes has itself defined that same hook already, that will
    take precedence.

    """

    state_class = BaseState

    @property
    def item_data(self: Union[Self, "DefaultObject"]):
        """Return a handler that provides unified data access for serialization."""
        from evennia_extensions.data_handlers import ObjectItemDataHandler

        return ObjectItemDataHandler(self)

    def get_object_state(
        self: Union[Self, "DefaultObject"], context: "SceneDataManager"
    ) -> BaseState:
        return self.state_class(obj=self, context=context)

    @property
    def trigger_registry(self: Union[Self, "DefaultObject"]) -> TriggerRegistry | None:
        """Return the trigger registry from our containing location."""
        if self.location:
            return self.location.trigger_registry
        return None

    @property
    def scene_data(self: Union[Self, "DefaultObject"]):
        """Return the SceneDataManager from our containing location."""
        if self.location:
            return self.location.scene_data
        return None

    @property
    def gender(self: Union[Self, "DefaultObject"]) -> str:
        """Gender used by funcparser pronoun helpers."""
        return "neutral"

    def get_display_name(
        self: Union[Self, "DefaultObject"], looker=None, **kwargs
    ) -> str:
        """Return the display name using state data when available."""
        scene_data = self.scene_data
        if scene_data:
            state = scene_data.get_state_by_pk(self.pk)
            if state:
                looker_state = scene_data.get_state_by_pk(looker.pk) if looker else None
                return state.get_display_name(looker_state, **kwargs)
        return super().get_display_name(looker, **kwargs)

    def at_post_move(self, source_location, move_type="move", **kwargs):
        """Register or unregister triggers when moving between rooms."""
        try:
            old_registry = source_location.trigger_registry
        except AttributeError:
            old_registry = None

        new_registry = self.trigger_registry

        if old_registry:
            for trigger in self.triggers.all():
                old_registry.unregister_trigger(trigger)

        if new_registry:
            for trigger in self.triggers.all():
                new_registry.register_trigger(trigger)

        super().at_post_move(source_location, move_type=move_type, **kwargs)
