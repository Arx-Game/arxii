"""Evennia command overrides related to perception."""

from typing import ClassVar

from commands.command import ArxCommand
from commands.dispatchers import BaseDispatcher, LocationDispatcher, TargetDispatcher
from commands.handlers.base import BaseHandler


class CmdLook(ArxCommand):
    """Examine a location or object."""

    key = "look"
    aliases: ClassVar[list[str]] = ["l", "ls", "glance"]
    locks = "cmd:all()"
    arg_regex = r"\s|$"
    dispatchers: ClassVar[list[BaseDispatcher]] = [
        LocationDispatcher(r"^$", BaseHandler(flow_name="look"), command_var="mode"),
        TargetDispatcher(
            r"^(?P<target>.+)$",
            BaseHandler(flow_name="look"),
            command_var="mode",
        ),
    ]


class CmdInventory(ArxCommand):
    """View inventory."""

    key = "inventory"
    aliases: ClassVar[list[str]] = ["inv", "i"]
    locks = "cmd:all()"
    dispatchers: ClassVar[list[BaseDispatcher]] = [
        BaseDispatcher(r"^$", BaseHandler(flow_name="inventory"))
    ]
