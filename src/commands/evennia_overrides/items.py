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
from actions.definitions.outfits import ApplyOutfitAction, UndressAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.items.models import Outfit


class CmdWear(ArxCommand):
    """Equip an item from your inventory, or wear a saved outfit.

    Telnet grammars:
        ``wear <item>``                 — equip an item from your inventory
        ``wear outfit <name>``          — apply a saved outfit by name
    """

    key = "wear"
    locks = "cmd:all()"
    action = EquipAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args("Wear what?")
        outfit_match = re.match(r"^outfit\s+(.+)$", args, flags=re.IGNORECASE)
        if outfit_match:
            outfit_name = outfit_match.group(1).strip()
            sheet = self.caller.sheet_data
            outfit = Outfit.objects.filter(
                character_sheet=sheet,
                name__iexact=outfit_name,
            ).first()
            if outfit is None:
                msg = f"You have no outfit named '{outfit_name}'."
                raise CommandError(msg)
            # Switch dispatch to ApplyOutfitAction for this invocation. Safe
            # because ``func()`` reads ``self.action`` after
            # ``resolve_action_args()``, and Evennia instantiates commands
            # per invocation.
            self.action = ApplyOutfitAction()
            return {"outfit_id": outfit.pk}
        return {"target": self.search_or_raise(args, location=self.caller)}


class CmdUndress(ArxCommand):
    """Remove all worn items at once. They go back to your inventory."""

    key = "undress"
    locks = "cmd:all()"
    action = UndressAction()

    def resolve_action_args(self) -> dict[str, Any]:
        return {}


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
