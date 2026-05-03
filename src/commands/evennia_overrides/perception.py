"""Evennia command overrides related to perception."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from actions.definitions.perception import (
    InventoryAction,
    LookAction,
    LookAtItemAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError

# Drilled-form regexes — try in order, fall through to plain look on no match.
_POSSESSIVE_RE = re.compile(r"^(.+?)'s\s+(.+)$", flags=re.IGNORECASE)
_ON_RE = re.compile(r"^(.+?)\s+on\s+(.+)$", flags=re.IGNORECASE)
_IN_RE = re.compile(r"^(.+?)\s+in\s+(.+)$", flags=re.IGNORECASE)


class CmdLook(ArxCommand):
    """Examine a location, character, or item.

    Telnet grammars:
        ``look``                          — look at the current location
        ``look <target>``                 — look at a character or object
        ``look <owner>'s <item>``         — examine an item worn on someone
        ``look <item> on <owner>``        — alternate syntax for worn items
        ``look <item> in <container>``    — examine an item inside a container
    """

    key = "look"
    aliases: ClassVar[list[str]] = ["l", "ls", "glance"]
    locks = "cmd:all()"
    arg_regex = r"\s|$"
    action = LookAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if not args:
            target = self.caller.location
            return {"target": target}

        # Try drilled forms first; on match, switch dispatch to LookAtItemAction.
        if match := _POSSESSIVE_RE.match(args):
            owner_name = match.group(1).strip()
            item_name = match.group(2).strip()
            return self._dispatch_at_owner(owner_name, item_name)
        if match := _ON_RE.match(args):
            item_name = match.group(1).strip()
            owner_name = match.group(2).strip()
            return self._dispatch_at_owner(owner_name, item_name)
        if match := _IN_RE.match(args):
            item_name = match.group(1).strip()
            container_name = match.group(2).strip()
            return self._dispatch_at_container(container_name, item_name)

        # Plain look — falls through to LookAction.
        target = self.caller.search(args)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}

    def _dispatch_at_owner(
        self,
        owner_name: str,
        item_name: str,
    ) -> dict[str, Any]:
        owner = self.caller.search(owner_name)
        if not owner:
            msg = f"Could not find '{owner_name}'."
            raise CommandError(msg)
        # Switch dispatch to LookAtItemAction. Safe because ``func()`` reads
        # ``self.action`` after ``resolve_action_args()``, and Evennia
        # instantiates commands per invocation.
        self.action = LookAtItemAction()
        return {"owner_id": owner.pk, "item_name": item_name}

    def _dispatch_at_container(
        self,
        container_name: str,
        item_name: str,
    ) -> dict[str, Any]:
        container = self.caller.search(container_name)
        if not container:
            msg = f"Could not find '{container_name}'."
            raise CommandError(msg)
        self.action = LookAtItemAction()
        return {"container_id": container.pk, "item_name": item_name}


class CmdInventory(ArxCommand):
    """View inventory."""

    key = "inventory"
    aliases: ClassVar[list[str]] = ["inv", "i"]
    locks = "cmd:all()"
    action = InventoryAction()
