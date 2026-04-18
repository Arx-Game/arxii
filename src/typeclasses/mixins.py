from functools import cached_property
from typing import TYPE_CHECKING, Self, Union

from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_handler import TriggerHandler

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

DEFAULT_GENDER = "neutral"


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
        self: Union[Self, "DefaultObject"],
        context: "SceneDataManager",
    ) -> BaseState:
        return self.state_class(obj=self, context=context)

    @cached_property
    def trigger_handler(self: Union[Self, "DefaultObject"]) -> TriggerHandler:
        """Populate-once cache of active triggers for this object."""
        return TriggerHandler(owner=self)

    @property
    def scene_data(self: Union[Self, "DefaultObject"]):
        """Return the SceneDataManager from our containing location."""
        if self.location:
            return self.location.scene_data
        return None

    @property
    def scene_state(self: Union[Self, "DefaultObject"]) -> BaseState | None:
        """Return the state object representing this entity in the scene."""
        scene_data = self.scene_data
        if scene_data:
            return scene_data.get_state_by_pk(self.pk)
        return None

    @property
    def gender(self: Union[Self, "DefaultObject"]) -> str:
        """Gender used by funcparser pronoun helpers."""
        return DEFAULT_GENDER

    def get_display_name(
        self: Union[Self, "DefaultObject"],
        looker=None,
        **kwargs,
    ) -> str:
        """Return the display name using state data when available."""
        state = self.scene_state
        if state:
            looker_state = looker.scene_state if looker else None
            return state.get_display_name(looker_state, **kwargs)
        return super().get_display_name(looker, **kwargs)

    def at_examined(self: Union[Self, "DefaultObject"], observer: "DefaultObject") -> bool:
        """Called when *observer* examines *self*.

        Emits EXAMINE_PRE (mutable — lets listeners veto/modify), then
        EXAMINED (frozen — post-event). Returns False if a reactive trigger
        cancelled the examine; callers should honour the return value.
        """
        from flows.emit import emit_event
        from flows.events.names import EventNames
        from flows.events.payloads import ExaminedPayload, ExaminePrePayload

        # For rooms, self is its own location; for characters/objects, use
        # the containing room.
        location = self.location if self.location is not None else self
        pre = ExaminePrePayload(observer=observer, target=self)
        stack = emit_event(
            EventNames.EXAMINE_PRE,
            pre,
            location=location,
        )
        if stack.was_cancelled():
            return False

        post = ExaminedPayload(observer=observer, target=self, result=None)
        emit_event(
            EventNames.EXAMINED,
            post,
            location=location,
        )
        return True

    def return_appearance(self, looker: "DefaultObject | None", **kwargs) -> str:
        """Return description string, after running the examine hook.

        If a reactive trigger cancels the examine, returns an empty string
        so that the calling command shows nothing (or its own fallback).
        """
        if looker is not None and not self.at_examined(looker):
            return ""
        return super().return_appearance(looker, **kwargs)  # type: ignore[misc]
