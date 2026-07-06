"""Telnet face of the existing SearchAction (#1866).

SearchAction already exists (actions/definitions/investigation.py) and is
web-dispatchable via the generic actions API; it had zero telnet command.
This is a bare ArxCommand delegate, mirroring CmdRest (commands/fatigue.py).
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.investigation import SearchAction
from commands.command import ArxCommand


class CmdSearch(ArxCommand):
    """Search your current room for clues.

    Usage:
      search
      investigate
    """

    key = "search"
    aliases: ClassVar[list[str]] = ["investigate"]
    locks = "cmd:all()"
    help_category = "General"
    action = SearchAction()
