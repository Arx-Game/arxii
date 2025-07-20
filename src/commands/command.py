"""
Commands

Commands describe the input the account can do to the game.

"""

from typing import Dict, List

from evennia.commands.command import Command

from commands.consts import HelpFileViewMode
from commands.exceptions import CommandError

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
    base_ascii_template = """
    """

    # base template for help viewed on webpage
    base_html_template = """
    """

    # List of dispatcher instances that map patterns of entered syntax to functions
    # or methods that we call with args derived from the command string.
    # All dispatchers can be found in dispatchers.py
    dispatchers = []

    # populated by the dispatcher that matches our syntax during parse()
    selected_dispatcher = None

    # values that are populated by the cmdhandler
    caller = None
    cmdname = None
    raw_cmdname = None
    args = None
    cmdset = None
    cmdset_providers = None
    session = None
    account = None
    raw_string = None

    def get_help(
        self, caller, cmdset, mode: HelpFileViewMode = HelpFileViewMode.TEXT
    ) -> str:
        """
        Override of Evennia's get_help. The parent class returns self.__doc__, but
        we want help to be more auto-generated than that. Instead, we'll have a
        separate method that will populate a template with the command key, args,
        and notes about each pattern the command is called with, as well as the
        overall command description.
        """
        # TODO: make other methods and template
        pass

    def get_template_context(
        self, caller=None, cmdset=None, mode: HelpFileViewMode = HelpFileViewMode.TEXT
    ) -> Dict:
        """
        Generates a dictionary of values that we can use to populate the jinja2
        template for our help. The caller, the cmdset, and all the command attributes
        such as the command's key, args, and description are all passed in here.

        """
        # note - objects may need to be serialized before they can be used in
        # a jinja2 template, so may need to cast values to string
        return {
            "caller": caller,
            "cmdset": cmdset,
            "key": self.key,
            "syntax_display": self.get_syntax_display(
                caller=caller, cmdset=cmdset, mode=mode
            ),
            "description": self.description,
            "view_mode": mode,
        }

    # noinspection PyUnusedLocal
    def get_syntax_strings(
        self, caller=None, cmdset=None, mode: HelpFileViewMode = HelpFileViewMode.TEXT
    ) -> List[str]:
        """
        Returns a list of strings that describe the usage for our commands. By
        default this is just the name of the command with no arguments.

        :param mode: The mode for which this will be viewed - in-game or on webpage
        :param caller: The caller who executed the command.
        :param cmdset: The cmdset that this command belongs to
        :return: A list of strings that describe the usage for our commands
        """
        return [
            dispatcher.bind(self).get_syntax_string(mode=mode)
            for dispatcher in self.dispatchers
        ]

    # noinspection PyUnusedLocal
    def get_template(
        self, caller=None, cmdset=None, mode: HelpFileViewMode = HelpFileViewMode.TEXT
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
        elif mode == HelpFileViewMode.WEB:
            return self.base_html_template
        # invalid mode
        raise ValueError(f"Unknown mode {mode}")

    def parse(self):
        """
        Override of base command parse method. It populates a number of values,
        but the important part for us is to populate our selected_dispatcher,
        if the args given by the player match any of the patterns defined in our
        dispatchers for the command.
        """
        super().parse()
        # bind selected_dispatcher
        for dispatcher in self.dispatchers:
            # bind the dispatcher to our command then see if it matches
            dispatcher.bind(self)
            if dispatcher.is_match():
                # we only find the first match and bail out
                self.selected_dispatcher = dispatcher
                break
        # do nothing if we don't find a selected_dispatcher: dispatch() will return
        # the error later when called.

    def func(self):
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
            self.msg(err)

    def dispatch(self):
        """
        The real meat of the command now. This finds our selected dispatcher, or
        raises a CommandError for invalid syntax. We then call our dispatcher,
        which may also raise a CommandError. We don't catch any errors here: we
        let them bubble up to func(), which catches them.
        :return:
        """
        if not self.selected_dispatcher:
            raise CommandError(
                f"Invalid usage:\n{self.get_syntax_display(
                    caller=self.caller,
                    cmdset=self.cmdset)}"
            )
        self.selected_dispatcher.execute_event()

    def get_syntax_display(
        self, caller=None, cmdset=None, mode: HelpFileViewMode = HelpFileViewMode.TEXT
    ) -> str:
        """
        Gets a string display of our syntax
        :return: String of our command's formatted syntax
        """
        newline = "\n" if mode == HelpFileViewMode.TEXT else "<br />"
        syntax_strings = self.get_syntax_strings(caller, cmdset, mode)
        return f"Syntax: {newline}{newline.join(syntax_strings)}"
