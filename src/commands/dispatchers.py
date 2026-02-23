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
from typing import TYPE_CHECKING, Any, cast

from commands.consts import HelpFileViewMode
from commands.exceptions import CommandError
from commands.frontend_types import FrontendDescriptor, ParamSchema

if TYPE_CHECKING:
    from commands.handlers.base import BaseHandler

__all__ = [
    "BaseDispatcher",
    "LocationDispatcher",
    "TargetDispatcher",
    "TargetTextDispatcher",
    "TextDispatcher",
]


class BaseDispatcher:
    """
    Dispatcher = *syntax layer only*
    --------------------------------
    •  Takes a regex *pattern* and a *handler instance* when constructed.
    •  Knows nothing about flows, events, or game-play rules.
    •  Resolves in-game objects from the text it parses and passes them –
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
        handler: "BaseHandler",
        *,
        use_raw_string: bool = False,
        command_var: str | None = None,
    ) -> None:
        self.pattern = re.compile(pattern)
        self.handler = handler  # already configured instance
        self.command: Any = None  # ArxCommand, will be set by bind()
        self.use_raw_string = use_raw_string
        self.command_var = command_var

    # ---------------------------------------------------------------------
    # High-level API
    # ---------------------------------------------------------------------
    def bind(self, command: Any) -> "BaseDispatcher":
        """Attach this dispatcher to a Concrete Command instance."""
        self.command = command
        return self

    def is_match(self) -> bool:
        """Return True if the command's input matches ``self.pattern``."""
        if not self.command:
            msg = "bind() must be called before is_match()."
            raise RuntimeError(msg)
        return bool(self.pattern.match(self._input_string()))

    def execute(self) -> None:
        """Parse input, resolve objects, and delegate to the handler."""
        if not self.is_match():
            msg = "execute() called but pattern does not match."
            raise RuntimeError(msg)

        kwargs = self.generate_kwargs()
        # The handler decides what to do with these kwargs.
        # Convention: it always accepts **kwargs plus "dispatcher" & "command"
        self.handler.run(dispatcher=self, command=self.command, **kwargs)

    def frontend_descriptor(self) -> FrontendDescriptor:
        """Return metadata describing this dispatcher for frontend use.

        ``params_schema`` describes arguments the client should collect. Each
        entry maps a parameter name to a schema with at least a ``type`` field.
        Dispatchers may include extra hints such as ``match`` for object
        lookups.

        Returns:
            FrontendDescriptor: Mapping containing action, params schema, icon
            and prompt fields for the client.
        """
        if self.command:
            action = self._command_alias()
            prompt = self.get_syntax_string()
        else:
            action = ""
            prompt = ""
        return FrontendDescriptor(
            action=action,
            params_schema={},
            icon="",
            prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Parsing helpers – meant to be customised in subclasses
    # ------------------------------------------------------------------
    def generate_kwargs(self) -> dict[str, object]:
        kwargs = self.get_basic_kwargs()
        kwargs.update(self.get_additional_kwargs())
        return kwargs

    def get_basic_kwargs(self) -> dict[str, object]:
        """Key/values every handler gets by default."""
        kwargs = {"caller": self.command.caller}
        if self.command_var:
            kwargs[self.command_var] = self._command_alias()
        return kwargs

    def get_additional_kwargs(self) -> dict[str, object]:
        """Sub-classes override to add target, amount, etc."""
        return {}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _input_string(self) -> str:
        if self.use_raw_string:
            return str(self.command.raw_string).strip()
        return str(self.command.args).strip()

    def _command_alias(self) -> str:
        """Return the preferred command name for frontend metadata."""
        try:
            cmdname = self.command.cmdname
        except AttributeError:
            cmdname = None
        if cmdname:
            return str(cmdname)
        try:
            return str(self.command.key)
        except AttributeError:
            return ""

    def get_syntax_string(self, mode: HelpFileViewMode = HelpFileViewMode.TEXT) -> str:
        """Return a human-readable representation of this dispatcher's syntax."""
        pattern = self.pattern.pattern
        pattern = pattern.removeprefix("^")
        pattern = pattern.removesuffix("$")
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
        handler: "BaseHandler",
        *,
        search_kwargs: dict[str, object] | None = None,
        command_var: str | None = None,
        target_match: str = "searchable_object",
    ) -> None:
        super().__init__(pattern, handler, command_var=command_var)
        self.search_kwargs = search_kwargs or {}
        self.target_match = target_match

    def get_additional_kwargs(self) -> dict[str, object]:
        match = self.pattern.match(self._input_string())
        if not match:
            msg = "Invalid syntax."
            raise CommandError(msg)
        return {"target": self._get_target(match)}

    def _get_target(self, match: re.Match[str]) -> Any:
        target_name = match.group("target")
        target = self.command.caller.search(target_name, **self.search_kwargs)
        if not target:
            msg = f"Could not find target '{target_name}'."
            raise CommandError(msg)
        return target

    def frontend_descriptor(self) -> FrontendDescriptor:
        """Include target parameter metadata for the frontend.

        The ``match`` field tells the client how to look up potential
        targets. By default we expect ``searchable_object`` which means an
        in-game object resolvable by the caller's regular search.
        """
        desc = super().frontend_descriptor()
        params_schema = cast(
            dict[str, ParamSchema],
            {"target": {"type": "string", "match": self.target_match}},
        )
        desc["params_schema"] = params_schema
        return desc


class LocationDispatcher(BaseDispatcher):
    """Dispatcher that always targets the caller's current location."""

    def __init__(
        self,
        pattern: str,
        handler: "BaseHandler",
        *,
        command_var: str | None = None,
    ) -> None:
        super().__init__(pattern, handler, command_var=command_var)

    def get_additional_kwargs(self) -> dict[str, object]:
        loc = self.command.caller.location
        if not loc:
            msg = "You are nowhere.  (No location set.)"
            raise CommandError(msg)
        return {"target": loc}


class TargetTextDispatcher(TargetDispatcher):
    """Resolve a target and capture additional text."""

    def get_additional_kwargs(self) -> dict[str, object]:
        match = self.pattern.match(self._input_string())
        if not match:
            msg = "Invalid syntax."
            raise CommandError(msg)
        target = self._get_target(match)
        return {"target": target, "text": match.group("text")}

    def frontend_descriptor(self) -> FrontendDescriptor:
        """Include target and text metadata for the frontend."""
        desc = super().frontend_descriptor()
        params_schema = cast(
            dict[str, ParamSchema],
            {
                "target": {"type": "string", "match": self.target_match},
                "text": {"type": "string"},
            },
        )
        desc["params_schema"] = params_schema
        return desc


class TextDispatcher(BaseDispatcher):
    """Dispatcher that captures free text."""

    def get_additional_kwargs(self) -> dict[str, object]:
        match = self.pattern.match(self._input_string())
        if not match:
            msg = "Invalid syntax."
            raise CommandError(msg)
        return {"text": match.group("text")}

    def frontend_descriptor(self) -> FrontendDescriptor:
        """Include text parameter metadata for the frontend."""
        desc = super().frontend_descriptor()
        params_schema = cast(dict[str, ParamSchema], {"text": {"type": "string"}})
        desc["params_schema"] = params_schema
        return desc
