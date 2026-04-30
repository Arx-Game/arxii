"""Telnet commands for item-specific actions: equip, unequip, put_in, take_out."""

from __future__ import annotations

from typing import Any

from actions.definitions.items import (
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
)
from commands.command import ArxCommand


class CmdWear(ArxCommand):
    """Equip (wear/wield) an item from your inventory."""

    key = "wear"
    locks = "cmd:all()"
    action = EquipAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Wear what?")
        return {"target": self.search_or_raise(name, location=self.caller)}


class CmdRemove(ArxCommand):
    """Unequip (remove) a worn item."""

    key = "remove"
    locks = "cmd:all()"
    action = UnequipAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Remove what?")
        return {"target": self.search_or_raise(name, location=self.caller)}


class CmdPut(ArxCommand):
    """Put an item from your inventory into a container."""

    key = "put"
    locks = "cmd:all()"
    action = PutInAction()

    def resolve_action_args(self) -> dict[str, Any]:
        item_name, container_name = self.parse_two_args(
            "in",
            empty_msg="Put what in what?",
            usage_msg="Usage: put <item> in <container>",
        )
        target = self.search_or_raise(item_name, location=self.caller)
        container = self.search_or_raise(container_name, location=self.caller)
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
        item_name, container_name = self.parse_two_args(
            "from",
            empty_msg="Withdraw what from what?",
            usage_msg="Usage: withdraw <item> from <container>",
        )
        container = self.search_or_raise(container_name, location=self.caller)
        # The item lives inside the container — search the container's contents.
        target = self.search_or_raise(
            item_name,
            location=container,
            not_found_msg=f"Could not find '{item_name}' in '{container_name}'.",
        )
        return {"target": target, "container": container}
