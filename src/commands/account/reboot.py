"""Staff ``@reboot``: stop and restart both Evennia daemons (#4001)."""

from typing import ClassVar

from commands.command import Command
from evennia_extensions.reboot import request_reboot


class CmdReboot(Command):
    """
    Restart the whole game: both the Server and the Portal.

    Usage:
        @reboot

    Everyone is told, both daemons stop, and the box's watchdog starts the
    game again within about a minute. Use this when the Portal has to reload
    its code or the whole process needs a clean start.

    This is not @reload, which restarts only the Server and keeps players
    connected (Evennia's @restart is an alias of @reload). It is not
    @shutdown either: @shutdown stops the game and leaves it down, on
    purpose, for work that needs the game off.
    """

    key = "@reboot"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:perm(reboot) or perm(Developer)"
    help_category = "System"

    def func(self) -> None:
        """Record the request, announce it, and shut both daemons down."""
        # Same guard as Evennia's @shutdown: only a connected staffer reboots.
        if not self.caller.sessions.get():
            return
        self.caller.msg("Restarting the game: both daemons stop now and come back shortly.")
        request_reboot(requested_by=self.caller.name)
