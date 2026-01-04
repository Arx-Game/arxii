"""Commands and serialization helpers."""

from collections.abc import Sequence
from typing import Any, ClassVar

from evennia.commands.command import Command

from commands.consts import HelpFileViewMode
from commands.descriptors import CommandDescriptor, DispatcherDescriptor
from commands.dispatchers import BaseDispatcher, TargetDispatcher, TargetTextDispatcher
from commands.exceptions import CommandError
from commands.frontend_types import FrontendDescriptor
from commands.types import Kwargs

# from evennia import default_cmds


class ArxCommand(Command):
    """
    Base command we'll use for all Arx II commands. We'll take a different approach
    than Evennia. Evennia has very 'fat' commands that contain all the business logic
    for any given action a player wishes to take. By contrast, we want our commands
    to be very thin - the only thing a command should be responsible for is to try to
    help determine what a player is attempting to do and to what, fetch whatever object
    the player is targeting if they can, then call whatever method or service function
    is appropriate for processing that action. We'll catch any exception raised by the
    process of trying to obtain a target or calling the method, and if so, report that
    message to the player. That is it. All logic should happen elsewhere: the command
    is purely a view/UI layer.
    """

    title = ""  # title that appears before syntax
    description = ""  # short description in help, appended after syntax

    # base template for in-game help
    base_ascii_template = "{title}\n\n{syntax_display}\n\n{description}"

    # base template for help viewed on webpage
    base_html_template = "<h2>{title}</h2><p>{syntax_display}</p><p>{description}</p>"

    # List of dispatcher instances that map patterns of entered syntax to functions
    # or methods that we call with args derived from the command string.
    # All dispatchers can be found in dispatchers.py
    dispatchers: ClassVar[Sequence[BaseDispatcher]] = ()

    def get_dispatchers(self) -> Sequence[BaseDispatcher]:
        """Return dispatchers available for this command instance."""

        return self.dispatchers

    # populated by the dispatcher that matches our syntax during parse()
    selected_dispatcher: BaseDispatcher | None = None

    # values that are populated by the cmdhandler
    caller: Any = None  # ObjectDB, but can be other types
    cmdname: str | None = None
    raw_cmdname: str | None = None
    args: str | None = None
    cmdset: Any = None  # CmdSet, but complex Evennia type
    cmdset_providers: Any = None  # Complex Evennia internal
    session: Any = None  # ServerSession, but complex Evennia type
    account: Any = None  # AccountDB, but can be other types
    raw_string: str | None = None
    obj: Any | None = None  # ObjectDB or exit target (set by Evennia)

    def msg(self, *args: object, **kwargs: Kwargs) -> None:
        """Send a message to the caller.

        This simply forwards all arguments to ``caller.msg`` without additional
        processing.

        Args:
            *args: Positional arguments for ``caller.msg``.
            **kwargs: Keyword arguments for ``caller.msg``.
        """
        self.caller.msg(*args, **kwargs)

    def get_help(
        self,
        caller: Any,
        cmdset: Any,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> str:
        """
        Override of Evennia's get_help. The parent class returns self.__doc__, but
        we want help to be more auto-generated than that. Instead, we'll have a
        separate method that will populate a template with the command key, args,
        and notes about each pattern the command is called with, as well as the
        overall command description.
        """
        context = self.get_template_context(caller, cmdset, mode=mode)
        template = self.get_template(caller, cmdset, mode=mode)
        return template.format(**context)

    def get_template_context(
        self,
        caller: Any = None,
        cmdset: Any = None,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> dict[str, Any]:
        """
        Generates a dictionary of values that we can use to populate the jinja2
        template for our help. The caller, the cmdset, and all the command attributes
        such as the command's key, args, and description are all passed in here.

        """
        # note - objects may need to be serialized before they can be used in
        # a jinja2 template, so may need to cast values to string
        description = self.description or (self.__doc__ or "").strip()
        title = self.title or self.key
        return {
            "caller": caller,
            "cmdset": cmdset,
            "key": self.key,
            "title": title,
            "syntax_display": self.get_syntax_display(
                caller=caller,
                cmdset=cmdset,
                mode=mode,
            ),
            "description": description,
            "view_mode": mode,
        }

    # noinspection PyUnusedLocal
    def get_syntax_strings(
        self,
        caller: Any = None,
        cmdset: Any = None,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> list[str]:
        """
        Returns a list of strings that describe the usage for our commands. By
        default this is just the name of the command with no arguments.

        :param mode: The mode for which this will be viewed - in-game or on webpage
        :param caller: The caller who executed the command.
        :param cmdset: The cmdset that this command belongs to
        :return: A list of strings that describe the usage for our commands
        """
        return [
            dispatcher.bind(self).get_syntax_string(mode=mode) for dispatcher in self.dispatchers
        ]

    # noinspection PyUnusedLocal
    def get_template(
        self,
        caller: Any = None,
        cmdset: Any = None,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> str:
        """
        Gets the template to use for our help file. It's not yet populated by our
        context, that happens in get_help.

        :param mode: The mode for which this will be viewed - in-game or on webpage
        :param caller: The caller who executed the command.
        :param cmdset: The cmdset that this command belongs to
        """
        if mode == HelpFileViewMode.TEXT:
            return self.base_ascii_template
        # mode == HelpFileViewMode.WEB:
        return self.base_html_template

    def parse(self) -> None:
        """
        Override of base command parse method. It populates a number of values,
        but the important part for us is to populate our selected_dispatcher,
        if the args given by the player match any of the patterns defined in our
        dispatchers for the command.
        """
        super().parse()
        # bind selected_dispatcher
        for dispatcher in self.get_dispatchers():
            # bind the dispatcher to our command then see if it matches
            dispatcher.bind(self)
            if dispatcher.is_match():
                # we only find the first match and bail out
                self.selected_dispatcher = dispatcher
                break
        # do nothing if we don't find a selected_dispatcher: dispatch() will return
        # the error later when called.

    def func(self) -> None:
        """
        func is called by the commandhandler once various hooks have been called,
        such as at_pre_cmd() and parse(). In standard Evennia, the func() command is
        very heavy with logic - everything the command does would be in here. We're
        taking a different approach: func should be extremely minimal, and is just
        about calling dispatch() while catching any raised CommandError. If we get
        an error, we'll just return it as a message to the caller.
        :return:
        """
        try:
            self.dispatch()
        except CommandError as err:
            self.msg(str(err))
            try:
                raw_string = self.raw_string
            except AttributeError:
                raw_string = ""
            self.msg(
                command_error={
                    "error": str(err),
                    "command": raw_string,
                },
            )

    def dispatch(self) -> None:
        """
        The real meat of the command now. This finds our selected dispatcher, or
        raises a CommandError for invalid syntax. We then call our dispatcher,
        which may also raise a CommandError. We don't catch any errors here: we
        let them bubble up to func(), which catches them.
        :return:
        """
        if not self.selected_dispatcher:
            msg = (
                f"Invalid usage:\n{self.get_syntax_display(caller=self.caller, cmdset=self.cmdset)}"
            )
            raise CommandError(
                msg,
            )
        self.selected_dispatcher.execute()

    def get_syntax_display(
        self,
        caller: Any = None,
        cmdset: Any = None,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> str:
        """
        Gets a string display of our syntax
        :return: String of our command's formatted syntax
        """
        newline = "\n" if mode == HelpFileViewMode.TEXT else "<br />"
        syntax_strings = self.get_syntax_strings(caller, cmdset, mode)
        if mode == HelpFileViewMode.TEXT:
            syntax_strings = [f"  {line}" for line in syntax_strings]
        return f"Syntax: {newline}{newline.join(syntax_strings)}"

    def to_payload(self, context: str | None = None) -> dict[str, Any]:
        """Serialize this command, its dispatchers and usage patterns.

        Args:
            context: Optional context filter such as ``"room"`` or ``"object"``.

        Returns:
            Serialized command description as a dictionary.
        """

        dispatcher_descs: list[DispatcherDescriptor] = []
        descriptors: list[FrontendDescriptor] = []
        for dispatcher in self.get_dispatchers():
            dispatcher.bind(self)
            disp_context = self._get_dispatcher_context(dispatcher)
            if context and disp_context != context:
                continue
            dispatcher_descs.append(
                DispatcherDescriptor(
                    syntax=dispatcher.get_syntax_string(),
                    context=disp_context,
                ),
            )
            descriptors.append(dispatcher.frontend_descriptor())

        descriptor = CommandDescriptor(
            key=self.key,
            aliases=sorted(self.aliases),
            dispatchers=dispatcher_descs,
            descriptors=descriptors,
        )
        return descriptor.to_dict()

    @staticmethod
    def _get_dispatcher_context(dispatcher: BaseDispatcher) -> str:
        """Get a context label for a dispatcher."""
        if isinstance(dispatcher, (TargetDispatcher, TargetTextDispatcher)):
            return "object"
        return "room"
