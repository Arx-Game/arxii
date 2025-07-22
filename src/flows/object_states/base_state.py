from collections import defaultdict
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from evennia.utils.utils import compress_whitespace, iter_to_str

if TYPE_CHECKING:
    from flows.context_data import ContextData
    from typeclasses.objects import Object


class BaseState:
    """
    BaseState wraps an Evennia object and provides mutable, ephemeral state that
    persists for the duration of a flow_stack's execution. Each state must be
    associated with a context, which is used to fetch and update related states.
    """

    def __init__(self, obj: "Object", context: "ContextData"):
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

    # ------------------------------------------------------------------
    # Appearance helpers (inspired by Evennia's DefaultObject)
    # ------------------------------------------------------------------

    @property
    def appearance_template(self) -> str:
        """Template used by :meth:`return_appearance`."""
        return "{name}\n{desc}"

    # Display-component methods
    def get_display_name(self, **kwargs) -> str:
        return self.name

    def get_extra_display_name_info(self, **kwargs) -> str:
        return ""

    def get_display_desc(self, **kwargs) -> str:
        return self.description

    def _get_contents(self, content_type: str):
        """Return contained states of the given type that should be displayed."""
        states = [
            self.context.get_state_by_pk(obj.pk)
            for obj in self.obj.contents_get(content_type=content_type)
        ]
        return [st for st in states if st and st.get_display_name()]

    def get_display_exits(self, **kwargs) -> str:
        exits = self._get_contents("exit")
        names = iter_to_str(
            (ex.get_display_name(**kwargs) for ex in exits), endsep=", and"
        )
        return f"|wExits:|n {names}" if names else ""

    def get_display_characters(self, **kwargs) -> str:
        characters = self._get_contents("character")
        names = iter_to_str(
            (ch.get_display_name(**kwargs) for ch in characters), endsep=", and"
        )
        return f"|wCharacters:|n {names}" if names else ""

    def get_display_things(self, **kwargs) -> str:
        things = self._get_contents("object")
        grouped = defaultdict(list)
        for thing in things:
            grouped[thing.get_display_name(**kwargs)].append(thing)
        thing_names = []
        for name, group in sorted(grouped.items()):
            count = len(group)
            obj = group[0].obj
            singular, plural = obj.get_numbered_name(count, None, key=name)
            thing_names.append(singular if count == 1 else plural)
        names = iter_to_str(thing_names, endsep=", and")
        return f"|wYou see:|n {names}" if names else ""

    def get_display_header(self, **kwargs) -> str:
        return ""

    def get_display_footer(self, **kwargs) -> str:
        return ""

    def format_appearance(self, appearance: str, **kwargs) -> str:
        return compress_whitespace(appearance).strip()

    def return_appearance(self, **kwargs) -> str:
        appearance = self.appearance_template.format(
            name=self.get_display_name(**kwargs),
            extra_name_info=self.get_extra_display_name_info(**kwargs),
            desc=self.get_display_desc(**kwargs),
            header=self.get_display_header(**kwargs),
            footer=self.get_display_footer(**kwargs),
            exits=self.get_display_exits(**kwargs),
            characters=self.get_display_characters(**kwargs),
            things=self.get_display_things(**kwargs),
        )
        return self.format_appearance(appearance, **kwargs)
