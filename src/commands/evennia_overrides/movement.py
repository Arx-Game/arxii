"""Evennia command overrides related to movement and item manipulation."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from actions.definitions.items import TakeOutAction
from actions.definitions.movement import DropAction, GetAction, GiveAction, HomeAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


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
        args = (self.args or "").strip()
        if not args:
            msg = "Get what?"
            raise CommandError(msg)
        match = re.match(r"^(.+?)\s+from\s+(.+)$", args, flags=re.IGNORECASE)
        if match:
            item_name = match.group(1).strip()
            container_name = match.group(2).strip()
            container = self.caller.search(container_name)
            if not container:
                msg = f"Could not find '{container_name}'."
                raise CommandError(msg)
            target = self.caller.search(item_name, location=container)
            if not target:
                msg = f"Could not find '{item_name}' in '{container_name}'."
                raise CommandError(msg)
            # Switch dispatch to TakeOutAction for this invocation. Safe because
            # ``func()`` reads ``self.action`` after ``resolve_action_args()``,
            # and Evennia instantiates commands per invocation.
            self.action = TakeOutAction()
            return {"target": target}
        target = self.caller.search(args)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}


class CmdDrop(ArxCommand):
    """Drop an item."""

    key = "drop"
    locks = "cmd:all()"
    action = DropAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if not args:
            msg = "Drop what?"
            raise CommandError(msg)
        target = self.caller.search(args, location=self.caller)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}


class CmdGive(ArxCommand):
    """Give an item to someone."""

    key = "give"
    locks = "cmd:all()"
    action = GiveAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        match = re.match(r"^(.+?)\s+to\s+(.+)$", args)
        if not match:
            msg = "Usage: give <item> to <recipient>"
            raise CommandError(msg)
        item_name = match.group(1).strip()
        recipient_name = match.group(2).strip()
        target = self.caller.search(item_name, location=self.caller)
        if not target:
            msg = f"Could not find '{item_name}'."
            raise CommandError(msg)
        recipient = self.caller.search(recipient_name)
        if not recipient:
            msg = f"Could not find '{recipient_name}'."
            raise CommandError(msg)
        return {"target": target, "recipient": recipient}


class CmdHome(ArxCommand):
    """Return to your home location."""

    key = "home"
    aliases: ClassVar[list[str]] = ["recall"]
    locks = "cmd:all()"
    action = HomeAction()
