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
from typing import Any, Dict, Optional

from commands.consts import HelpFileViewMode
from commands.exceptions import CommandError

__all__ = [
    "BaseDispatcher",
    "TargetDispatcher",
    "LocationDispatcher",
    "TextDispatcher",
    "TargetTextDispatcher",
]


class BaseDispatcher:
    """
    Dispatcher = *syntax layer only*
    --------------------------------
    •  Takes a regex *pattern* and a *handler instance* when constructed.
    •  Knows nothing about flows, events, or game‑play rules.
    •  Resolves in‑game objects from the text it parses and passes them –
       together with literal args – to the handler's ``run`` method.

    Instantiation
    -------------
    dispatcher = TargetDispatcher(
        pattern=r"^look (?P<target>.+)$",
        handler=BaseHandler(
            flow_name="examine_flow",
            prerequisite_events=("prereq.volition",),
        ),
    )

    A command can keep a *list* of such dispatchers, bind each of them to
    itself, and ask *each* "do you match?" until one succeeds.
    """

    def __init__(
        self,
        pattern: str,
        handler,
        *,
        use_raw_string: bool = False,
        command_var: str | None = None,
    ) -> None:
        self.pattern = re.compile(pattern)
        self.handler = handler  # already configured instance
        self.command = None  # will be set by bind()
        self.use_raw_string = use_raw_string
        self.command_var = command_var

    # ---------------------------------------------------------------------
    # High‑level API
    # ---------------------------------------------------------------------
    def bind(self, command):
        """Attach this dispatcher to a Concrete Command instance."""
        self.command = command
        return self

    def is_match(self) -> bool:
        """Return True if the command's input matches ``self.pattern``."""
        if not self.command:
            raise RuntimeError("bind() must be called before is_match().")
        return bool(self.pattern.match(self._input_string()))

    def execute(self):
        """Parse input, resolve objects, and delegate to the handler."""
        if not self.is_match():
            raise RuntimeError("execute() called but pattern does not match.")

        kwargs = self.generate_kwargs()
        # The handler decides what to do with these kwargs.
        # Convention: it always accepts **kwargs plus "dispatcher" & "command"
        self.handler.run(dispatcher=self, command=self.command, **kwargs)

    # ------------------------------------------------------------------
    # Parsing helpers – meant to be customised in subclasses
    # ------------------------------------------------------------------
    def generate_kwargs(self) -> Dict[str, Any]:
        kwargs = self.get_basic_kwargs()
        kwargs.update(self.get_additional_kwargs())
        return kwargs

    def get_basic_kwargs(self) -> Dict[str, Any]:
        """Key/values every handler gets by default."""
        kwargs = {"caller": self.command.caller}
        if self.command_var:
            alias = getattr(self.command, "cmdname", None) or getattr(
                self.command, "key", ""
            )
            kwargs[self.command_var] = alias
        return kwargs

    def get_additional_kwargs(self) -> Dict[str, Any]:
        """Sub‑classes override to add target, amount, etc."""
        return {}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _input_string(self) -> str:
        if self.use_raw_string:
            return self.command.raw_string.strip()
        return self.command.args.strip()

    def get_syntax_string(self, mode: HelpFileViewMode = HelpFileViewMode.TEXT) -> str:
        """Return a human-readable representation of this dispatcher's syntax."""
        pattern = self.pattern.pattern
        if pattern.startswith("^"):
            pattern = pattern[1:]
        if pattern.endswith("$"):
            pattern = pattern[:-1]
        # normalize whitespace tokens
        pattern = re.sub(r"\\s\+", " ", pattern)
        # replace named groups with simple placeholders
        pattern = re.sub(r"\(\?P<(\w+)>[^)]+\)", r"<\1>", pattern)
        # unescape common characters
        pattern = pattern.replace("\\'", "'").replace('\\"', '"')
        pattern = re.sub(r"\s+", " ", pattern)
        return f"{self.command.key} {pattern}".strip()


class TargetDispatcher(BaseDispatcher):
    """Dispatcher that resolves a single *target* from caller's search scope."""

    def __init__(
        self,
        pattern: str,
        handler,
        *,
        search_kwargs: Optional[Dict[str, Any]] = None,
        command_var: str | None = None,
    ) -> None:
        super().__init__(pattern, handler, command_var=command_var)
        self.search_kwargs = search_kwargs or {}

    def get_additional_kwargs(self) -> Dict[str, Any]:
        match = self.pattern.match(self._input_string())
        if not match:
            raise CommandError("Invalid syntax.")
        return {"target": self._get_target(match)}

    def _get_target(self, match):
        target_name = match.group("target")
        target = self.command.caller.search(target_name, **self.search_kwargs)
        if not target:
            raise CommandError(f"Could not find target '{target_name}'.")
        return target


class LocationDispatcher(BaseDispatcher):
    """Dispatcher that always targets the caller's current location."""

    def __init__(
        self, pattern: str, handler, *, command_var: str | None = None
    ) -> None:
        super().__init__(pattern, handler, command_var=command_var)

    def get_additional_kwargs(self) -> Dict[str, Any]:
        loc = self.command.caller.location
        if not loc:
            raise CommandError("You are nowhere.  (No location set.)")
        return {"target": loc}


class TargetTextDispatcher(TargetDispatcher):
    """Resolve a target and capture additional text."""

    def get_additional_kwargs(self) -> Dict[str, Any]:
        match = self.pattern.match(self._input_string())
        if not match:
            raise CommandError("Invalid syntax.")
        target = self._get_target(match)
        return {"target": target, "text": match.group("text")}


class TextDispatcher(BaseDispatcher):
    """Dispatcher that captures free text."""

    def get_additional_kwargs(self) -> Dict[str, Any]:
        match = self.pattern.match(self._input_string())
        if not match:
            raise CommandError("Invalid syntax.")
        return {"text": match.group("text")}
