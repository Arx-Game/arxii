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

        # Try drilled forms first; if any matches the regex but the
        # owner/container can't be found, fall through to plain search on
        # the full args. This keeps three classes of input working:
        #   - Apostrophe names (``L'Aurelia`` → owner ``L`` not found,
        #     fall through to plain search)
        #   - ``look bob in armor`` when "armor" isn't a real container
        #     (intent: look at bob)
        #   - Items literally named ``bob's hat`` when no character bob
        #     is present
        if match := _POSSESSIVE_RE.match(args):
            owner_name = match.group(1).strip()
            item_name = match.group(2).strip()
            result = self._try_dispatch_at_owner(owner_name, item_name)
            if result is not None:
                return result
        if match := _ON_RE.match(args):
            item_name = match.group(1).strip()
            owner_name = match.group(2).strip()
            result = self._try_dispatch_at_owner(owner_name, item_name)
            if result is not None:
                return result
        if match := _IN_RE.match(args):
            item_name = match.group(1).strip()
            container_name = match.group(2).strip()
            result = self._try_dispatch_at_container(container_name, item_name)
            if result is not None:
                return result

        # Plain look — falls through to LookAction.
        target = self.caller.search(args)
        if not target:
            msg = f"Could not find '{args}'."
            raise CommandError(msg)
        return {"target": target}

    def _try_dispatch_at_owner(
        self,
        owner_name: str,
        item_name: str,
    ) -> dict[str, Any] | None:
        """Resolve owner and switch to LookAtItemAction; return ``None`` to fall through.

        Uses ``quiet=True`` so failed lookups don't message the user — the
        caller will retry as a plain search. ``quiet=True`` returns a
        list; when multiple match we pick the first (same heuristic
        Evennia would use after disambiguation).
        """
        results = self.caller.search(owner_name, quiet=True)
        if not results:
            return None
        owner = results[0] if isinstance(results, list) else results
        # Switch dispatch to LookAtItemAction. Safe because ``func()`` reads
        # ``self.action`` after ``resolve_action_args()``, and Evennia
        # instantiates commands per invocation.
        self.action = LookAtItemAction()
        return {"owner_id": owner.pk, "item_name": item_name}

    def _try_dispatch_at_container(
        self,
        container_name: str,
        item_name: str,
    ) -> dict[str, Any] | None:
        """Resolve container and switch to LookAtItemAction; return ``None`` to fall through."""
        results = self.caller.search(container_name, quiet=True)
        if not results:
            return None
        container = results[0] if isinstance(results, list) else results
        self.action = LookAtItemAction()
        return {"container_id": container.pk, "item_name": item_name}


class CmdInventory(ArxCommand):
    """View inventory."""

    key = "inventory"
    aliases: ClassVar[list[str]] = ["inv", "i"]
    locks = "cmd:all()"
    action = InventoryAction()
