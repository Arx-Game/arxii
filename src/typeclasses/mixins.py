from typing import TYPE_CHECKING, Self, Union

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from flows.context_data import ContextData


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
        return self.db

    def get_object_state(
        self: Union[Self, "DefaultObject"], context: "ContextData"
    ) -> BaseState:
        return self.state_class(obj=self, context=context)
