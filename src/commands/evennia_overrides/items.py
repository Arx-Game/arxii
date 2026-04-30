"""Telnet commands for item-specific actions: equip, unequip, put_in, take_out."""

from __future__ import annotations

import re
from typing import Any

from actions.definitions.items import (
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdWear(ArxCommand):
    """Equip (wear/wield) an item from your inventory."""

    key = "wear"
    locks = "cmd:all()"
    action = EquipAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if not args:
            msg = "Wear what?"
            raise CommandError(msg)
        target = self.caller.search(args, location=self.caller)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}


class CmdRemove(ArxCommand):
    """Unequip (remove) a worn item."""

    key = "remove"
    locks = "cmd:all()"
    action = UnequipAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if not args:
            msg = "Remove what?"
            raise CommandError(msg)
        target = self.caller.search(args, location=self.caller)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}


class CmdPut(ArxCommand):
    """Put an item from your inventory into a container."""

    key = "put"
    locks = "cmd:all()"
    action = PutInAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        match = re.match(r"^(.+?)\s+in\s+(.+)$", args)
        if not match:
            msg = "Usage: put <item> in <container>"
            raise CommandError(msg)
        item_name = match.group(1).strip()
        container_name = match.group(2).strip()
        target = self.caller.search(item_name, location=self.caller)
        if not target:
            msg = f"Could not find '{item_name}'."
            raise CommandError(msg)
        container = self.caller.search(container_name, location=self.caller)
        if not container:
            msg = f"Could not find '{container_name}'."
            raise CommandError(msg)
        return {"target": target, "container": container}


class CmdWithdraw(ArxCommand):
    """Take an item out of a container in your inventory.

    Uses the key ``withdraw`` to avoid colliding with ``CmdGet``'s ``take``
    alias. Telnet: ``withdraw <item> from <container>``.
    """

    key = "withdraw"
    locks = "cmd:all()"
    action = TakeOutAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        match = re.match(r"^(.+?)\s+from\s+(.+)$", args)
        if not match:
            msg = "Usage: withdraw <item> from <container>"
            raise CommandError(msg)
        item_name = match.group(1).strip()
        container_name = match.group(2).strip()
        container = self.caller.search(container_name, location=self.caller)
        if not container:
            msg = f"Could not find '{container_name}'."
            raise CommandError(msg)
        # The item lives inside the container — search the container's contents.
        target = self.caller.search(item_name, location=container)
        if not target:
            msg = f"Could not find '{item_name}' in '{container_name}'."
            raise CommandError(msg)
        return {"target": target, "container": container}
