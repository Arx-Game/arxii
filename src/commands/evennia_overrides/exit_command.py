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

    def parse(self):
        """Set up dispatchers dynamically based on the exit object."""
        # Set up dispatchers based on the exit object (available as self.obj)
        if self.obj:
            self.dispatchers = [
                ExitDispatcher(r"^$", BaseHandler(flow_name="exit_traverse"), self.obj),
            ]

        # Call parent parse to handle the rest
        super().parse()
