"""
Commands

Commands describe the input the account can do to the game.

"""

from typing import Dict, List

from evennia.commands.command import Command

from commands.consts import HelpFileViewMode

# from evennia import default_cmds


class ArxCommand(Command):
    """
    Base command we'll use for all Arx II commands. We'll take a different approach
    than Evennia. Evennia has very 'fat' commands that contain all the business logic
    for any given action a player wishes to take. By contrast, we want our commands
    to be very thing - the only thing a command should be responsible for is to try to
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
            "syntax_strings": self.get_syntax_strings(
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
