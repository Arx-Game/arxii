"""Telnet face of the fatigue-rest action (#1491).

Thin command: parses no args and delegates directly to the REGISTRY
``RestAction`` so telnet players can spend AP to become Well-Rested.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.fatigue import RestAction
from commands.command import ArxCommand


class CmdRest(ArxCommand):
    """Spend AP to rest, gaining Well-Rested for the next dawn reset.

    Usage:
      rest
    """

    key = "rest"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = RestAction()
