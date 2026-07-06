"""Telnet commands for the #1909 physical-currency interplay: deposit/steal/secure.

``withdraw coins <amount>`` rides the existing ``CmdWithdraw`` in
``commands/evennia_overrides/items.py`` (the ``withdraw`` command key was
already spoken for by ``TakeOutAction``) and ``give <amount> to <recipient>``
rides ``CmdGive`` in ``commands/evennia_overrides/movement.py`` (per-invocation
action swap, like ``CmdGet``'s ``from <container>`` branch) — see those files.
This module holds the remaining new commands: ``deposit``, ``steal``, ``secure``.
"""

from __future__ import annotations

import re
from typing import Any

from actions.definitions.currency import DepositCoinsAction
from actions.definitions.items import SetContainerPolicyAction, StealAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_SECURE_USAGE = "Usage: secure <container>=<open|friends|owner_only>"
_DEFAULT_LOCKS = "cmd:all()"


class CmdDeposit(ArxCommand):
    """Deposit a physical coin (loose cache or grand coin) into your purse.

    Telnet: ``deposit <item>``.
    """

    key = "deposit"
    locks = _DEFAULT_LOCKS
    action = DepositCoinsAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Deposit what?")
        return {"target": self.search_or_raise(name, location=self.caller)}


class CmdSteal(ArxCommand):
    """Take an item that plain ``get``/``withdraw`` refuses — with consequences (#1909).

    Telnet grammars (mirrors ``CmdGet``):
        ``steal <item>``                  — from the room or a character present
        ``steal <item> from <container>`` — from inside a container

    Unlike ``CmdGet``, this always dispatches ``StealAction`` — there is no
    plain-take fallback here.
    """

    key = "steal"
    locks = _DEFAULT_LOCKS
    action = StealAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args("Steal what?")
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
            return {"target": target}
        return {"target": self.search_or_raise(args)}


class CmdSecure(ArxCommand):
    """Set who may take items out of a container you own (#1909).

    Usage:
      secure <container>=<open|friends|owner_only>
    """

    key = "secure"
    locks = _DEFAULT_LOCKS
    action = SetContainerPolicyAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = self.require_args(_SECURE_USAGE)
        if "=" not in raw:
            raise CommandError(_SECURE_USAGE)
        container_name, policy_name = (part.strip() for part in raw.split("=", 1))
        if not container_name or not policy_name:
            raise CommandError(_SECURE_USAGE)
        container = self.search_or_raise(container_name, location=self.caller)
        return {"target": container, "policy": policy_name.lower()}
