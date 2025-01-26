"""
Dispatchers are classes that take a pattern of syntax used for a command and map it
to the behaviors that we want to occur. Each Dispatcher should take a regex pattern
to match and an Event class. The Dispatcher is responsible for extracting values
from the input string, finding database objects based on the extracted values, and
instantiating the Event with the necessary arguments.

Each Dispatcher subclass handles the specifics of how to search for and validate the
targets based on its type. For example, a LocationDispatcher might get its target
from the character's location, while a TargetDispatcher gets its target from the input
string and performs a search in the caller's context.

The Dispatcher raises errors if it cannot find any expected targets from the input
string passed to it. The Event class then determines if the action can be performed
and orchestrates the action, emitting signals as necessary.

For example, suppose we want to create a command for 'look', which has three patterns
for its usage:
1. "look" with no arguments will examine the character's room.
2. "look <target>" will examine a given object matching the target.
3. "look <target>'s <possession>" will examine an object in the inventory of the
target.

Each of these is a regex pattern that will be captured by a Dispatcher object with the
behaviors that we want to create: instantiating an Event (e.g., ExamineEvent) with the
extracted arguments. The Dispatchers are added to a list in a Command, like so:

# inside our Look command
dispatchers = [
    LocationDispatcher(r"^look$", handler_class=ExamineEventHandler),
    TargetDispatcher(r"^look\\s+(?P<target>.+)$",
                     handler_class=ExamineEventHandler),
]
(note - have to escape the regex in the example because the entire docstring is not,
itself, a raw string)

Each Dispatcher is instantiated and saved in that list. When parse() is run, we find
which Dispatcher, if any, matches our pattern and binds it to our current command
instance. The found Dispatcher is then assigned to self.selected_dispatcher. Later,
if no selected_dispatcher is present, we'll return an invalid usage error to the user
with a list of proper syntax. Note that the order of the dispatchers is significant—
much like urls.py for Django, we match the first pattern found and then quit, so you
must ensure you go from more specific to more general.

The Dispatcher is responsible for finding all arguments for the Event it will
instantiate. If any targets can't be found, it should raise a CommandError. The Event
will then determine if those targets are valid for the action that is being taken—
the Dispatcher should only be responsible for determining if the syntax is correct and
discovering the player's intentions.
"""

import re
from typing import Dict

from commands.exceptions import CommandError


class BaseDispatcher:
    """
    The base class for all dispatchers. At their most basic level, they have an event
    handler to call and a regex pattern to match.
    """

    def __init__(self, pattern, handler_class, use_raw_string=False):
        self.pattern = re.compile(pattern)
        self.handler_class = handler_class
        self.handler = None
        self.command = None
        self.use_raw_string = use_raw_string

    def bind(self, command):
        self.command = command
        return self

    def is_match(self) -> bool:
        """Determines if our command is a match for our pattern."""
        if not self.command:
            raise RuntimeError("bind() must be called before calling is_match().")
        # determine if command.args match our pattern
        return bool(self.pattern.match(self.input_string.strip()))

    @property
    def input_string(self):
        if self.use_raw_string:
            return self.command.raw_string.strip()
        return self.command.args.strip()

    def execute_handler(self):
        """
        Instantiates our handler and gathers the arguments for it then calls it.
        """
        kwargs = self.generate_kwargs()
        self.instantiate_handler(**kwargs)
        self.handler.execute()

    def generate_kwargs(self) -> Dict:
        """
        This parses our input string and derives values from it which will
        then be searched for, raising CommandError if we can't find any valid targets.
        """
        kwargs = self.get_basic_kwargs()
        kwargs.update(self.get_additional_kwargs())
        return kwargs

    def get_basic_kwargs(self) -> Dict:
        context = {
            "command": self.command,
            "dispatcher": self,
        }
        return {
            "context": context,
        }

    # noinspection PyMethodMayBeStatic
    def get_additional_kwargs(self) -> Dict:
        """
        Overridden in subclasses to parse additional targets from the input string,
        performing database searches and raising errors when we can't resolve them.
        :rtype: dict
        :return: dict of values that handlers will take as keyword arguments. Most
            handlers will have a 'target' kwarg.
        """
        return {}

    def instantiate_handler(self, **kwargs):
        self.handler = self.handler_class(caller=self.command.caller, **kwargs)
        return self.handler


class TargetDispatcher(BaseDispatcher):
    """
    Dispatcher for handling commands that target a specific object in the caller's context.
    """

    def __init__(self, pattern, handler_class, search_kwargs=None):
        super().__init__(pattern, handler_class)
        self.search_kwargs = search_kwargs or {}

    def get_additional_kwargs(self) -> Dict:
        match = self.pattern.match(self.input_string)
        if not match:
            raise CommandError("Invalid syntax.")
        return {"target": self.get_target(match)}

    def get_target(self, match):
        target_name = match.group("target")
        target = self.command.caller.search(target_name, **self.search_kwargs)
        if not target:
            raise CommandError(f"Could not find target '{target_name}'.")


class LocationDispatcher(BaseDispatcher):
    """
    Dispatcher for handling commands that target the character's current location.
    """

    def get_additional_kwargs(self) -> Dict:
        if not self.command.caller.location:
            raise CommandError("You have no location!")

        return {"target": self.command.caller.location}
