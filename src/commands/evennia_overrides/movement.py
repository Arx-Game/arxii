"""Evennia command overrides related to movement and item manipulation."""

from typing import ClassVar

from commands.command import ArxCommand
from commands.dispatchers import BaseDispatcher, TargetDispatcher
from commands.exceptions import CommandError
from commands.handlers.base import BaseHandler


class CmdGet(ArxCommand):
    """Pick up an item."""

    key = "get"
    aliases: ClassVar[list[str]] = ["take"]
    locks = "cmd:all()"

    dispatchers: ClassVar[tuple[TargetDispatcher, ...]] = (
        TargetDispatcher(r"^(?P<target>.+)$", BaseHandler(flow_name="get")),
    )


class CmdDrop(ArxCommand):
    """Drop an item."""

    key = "drop"
    locks = "cmd:all()"

    dispatchers: ClassVar[tuple[TargetDispatcher, ...]] = (
        TargetDispatcher(r"^(?P<target>.+)$", BaseHandler(flow_name="drop")),
    )


class GiveDispatcher(TargetDispatcher):
    """Resolve both target item and recipient."""

    def get_additional_kwargs(self):
        match = self.pattern.match(self._input_string())
        if not match:
            msg = "Invalid syntax."
            raise CommandError(msg)
        target = self._get_target(match)
        recipient_name = match.group("recipient")
        recipient = self.command.caller.search(recipient_name)
        if not recipient:
            msg = f"Could not find target '{recipient_name}'."
            raise CommandError(msg)
        return {"target": target, "recipient": recipient}


class CmdGive(ArxCommand):
    """Give an item to someone."""

    key = "give"
    locks = "cmd:all()"

    dispatchers: ClassVar[tuple[GiveDispatcher, ...]] = (
        GiveDispatcher(
            r"^(?P<target>.+?)\s+to\s+(?P<recipient>.+)$",
            BaseHandler(flow_name="give"),
        ),
    )


class CmdHome(ArxCommand):
    """Return to your home location."""

    key = "home"
    aliases: ClassVar[list[str]] = ["recall"]
    locks = "cmd:all()"

    dispatchers: ClassVar[tuple[BaseDispatcher, ...]] = (
        BaseDispatcher(r"^$", BaseHandler(flow_name="home")),
    )
