"""Evennia command overrides related to perception."""

from commands.command import ArxCommand
from commands.dispatchers import BaseDispatcher, LocationDispatcher, TargetDispatcher
from commands.handlers.base import BaseHandler


class CmdLook(ArxCommand):
    """Examine a location or object."""

    key = "look"
    aliases = ["l", "ls", "glance"]
    locks = "cmd:all()"
    arg_regex = r"\s|$"
    dispatchers = [
        LocationDispatcher(r"^$", BaseHandler(flow_name="look"), command_var="mode"),
        TargetDispatcher(
            r"^(?P<target>.+)$", BaseHandler(flow_name="look"), command_var="mode"
        ),
    ]


class CmdInventory(ArxCommand):
    """View inventory."""

    key = "inventory"
    aliases = ["inv", "i"]
    locks = "cmd:all()"
    dispatchers = [BaseDispatcher(r"^$", BaseHandler(flow_name="inventory"))]
