"""Evennia command overrides related to movement and item manipulation."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from actions.definitions.items import TakeOutAction
from actions.definitions.movement import DropAction, GetAction, GiveAction, HomeAction
from commands.command import ArxCommand


class CmdGet(ArxCommand):
    """Pick up an item from the room or take an item out of a container.

    Telnet grammars:
        ``get <item>`` / ``take <item>``                 — pick up from the room
        ``get <item> from <container>``                  — take out of a container
        ``take <item> from <container>`` (alias)
    """

    key = "get"
    aliases: ClassVar[list[str]] = ["take"]
    locks = "cmd:all()"
    action = GetAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args("Get what?")
        # ``from <container>`` form switches to TakeOutAction. Try the
        # connector form first; if it doesn't match, fall back to single-target.
        match = re.match(r"^(.+?)\s+from\s+(.+)$", args, flags=re.IGNORECASE)
        if match:
            item_name = match.group(1).strip()
            container_name = match.group(2).strip()
            container = self.search_or_raise(container_name)
            target = self.search_or_raise(
                item_name,
                location=container,
                not_found_msg=f"Could not find '{item_name}' in '{container_name}'.",
            )
            # Switch dispatch to TakeOutAction for this invocation. Safe because
            # ``func()`` reads ``self.action`` after ``resolve_action_args()``,
            # and Evennia instantiates commands per invocation.
            self.action = TakeOutAction()
            return {"target": target}
        return {"target": self.search_or_raise(args)}


class CmdDrop(ArxCommand):
    """Drop an item."""

    key = "drop"
    locks = "cmd:all()"
    action = DropAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Drop what?")
        return {"target": self.search_or_raise(name, location=self.caller)}


class CmdGive(ArxCommand):
    """Give an item to someone."""

    key = "give"
    locks = "cmd:all()"
    action = GiveAction()

    def resolve_action_args(self) -> dict[str, Any]:
        item_name, recipient_name = self.parse_two_args(
            "to",
            empty_msg="Give what to whom?",
            usage_msg="Usage: give <item> to <recipient>",
        )
        target = self.search_or_raise(item_name, location=self.caller)
        recipient = self.search_or_raise(recipient_name)
        return {"target": target, "recipient": recipient}


class CmdHome(ArxCommand):
    """Return to your home location."""

    key = "home"
    aliases: ClassVar[list[str]] = ["recall"]
    locks = "cmd:all()"
    action = HomeAction()
