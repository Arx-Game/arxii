"""Evennia command overrides related to perception."""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.perception import InventoryAction, LookAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdLook(ArxCommand):
    """Examine a location or object."""

    key = "look"
    aliases: ClassVar[list[str]] = ["l", "ls", "glance"]
    locks = "cmd:all()"
    arg_regex = r"\s|$"
    action = LookAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if not args:
            target = self.caller.location
        else:
            target = self.caller.search(args)
            if not target:
                msg = f"Could not find '{args}'."
                raise CommandError(msg)
        return {"target": target}


class CmdInventory(ArxCommand):
    """View inventory."""

    key = "inventory"
    aliases: ClassVar[list[str]] = ["inv", "i"]
    locks = "cmd:all()"
    action = InventoryAction()
