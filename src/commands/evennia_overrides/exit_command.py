"""Exit command that uses the flow system."""

from commands.command import ArxCommand
from commands.dispatchers import BaseDispatcher
from commands.handlers.base import BaseHandler


class ExitDispatcher(BaseDispatcher):
    """Dispatcher that provides the exit as the target."""

    def __init__(self, pattern, handler, exit_obj):
        super().__init__(pattern, handler)
        self.exit_obj = exit_obj

    def get_additional_kwargs(self):
        """Provide the exit as the target for the flow."""
        return {"target": self.exit_obj}


class CmdExit(ArxCommand):
    """
    Traverse an exit.

    This command is dynamically created for each exit and allows characters
    to traverse exits using the flow system.
    """

    def __init__(self, exit_obj):
        """Initialize the command for a specific exit."""
        super().__init__()
        self.exit_obj = exit_obj
        self.key = exit_obj.key
        self.aliases = (
            list(exit_obj.aliases.all()) if hasattr(exit_obj.aliases, "all") else []
        )
        self.locks = "cmd:all()"

        # Create a dispatcher that targets this specific exit
        self.dispatchers = [
            ExitDispatcher(r"^$", BaseHandler(flow_name="exit_traverse"), exit_obj)
        ]
