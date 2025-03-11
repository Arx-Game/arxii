from typing import TYPE_CHECKING

from django.utils.functional import cached_property

if TYPE_CHECKING:
    from flows.context_data import ContextData
    from typeclasses.objects import Object


class BaseState:
    """
    BaseState wraps an Evennia object and provides mutable, ephemeral state that
    persists for the duration of a flow_stack's execution. Each state must be
    associated with a context, which is used to fetch and update related states.
    """

    def __init__(self, obj: Object, context: ContextData):
        """
        Initializes the state with an Evennia object and its associated context.

        :param obj: The underlying Evennia object.
        :param context: The context in which this state exists. This must be provided
                        so that any changes persist during the flow's execution.
        """
        self.obj = obj
        self.context = context

    @cached_property
    def name(self):
        # Compute the default name from the Evennia object.
        return self.obj.key

    @cached_property
    def description(self):
        # Use item_data instead of .db to get the description.
        try:
            return self.obj.item_data.desc or "You see nothing of note."
        except AttributeError:
            return "You see nothing of note."

    @property
    def template(self):
        # A simple default template.
        return "{name}: {description}"

    @property
    def contents(self):
        """
        Returns a list of contained state objects. It uses the context to convert each
        contained Evennia object (from self.obj.contents) into its corresponding state.
        """
        # Assumes self.obj.contents is a list of Evennia objects.
        return [self.context.get_state_by_pk(obj.pk) for obj in self.obj.contents]

    def get_categories(self):
        """
        Returns additional category data as a dictionary. Subclasses can override
        this method to supply extra template keys.
        """
        return {}
