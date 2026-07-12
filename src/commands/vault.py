"""Vault access-list management telnet command — the ``vault`` namespace (#2179).

A single command routes the vault access-list verbs through the shared
``dispatch_player_action`` seam. No game logic lives here; the command
only parses telnet text and resolves objects before dispatching to the
REGISTRY actions in ``actions/definitions/vault.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Subverb name constants (used in comparisons — avoids STRING_LITERAL lint).
_SUBVERB_STATUS = "status"
_SUBVERB_ACCESS = "access"
_SUBVERB_LIST = "list"
_SUBVERB_ADD = "add"
_SUBVERB_REMOVE = "remove"
_PREFIX_ORG = "/org"

# subverb → registry action key.
_ACCESS_SUBVERBS: dict[str, str] = {
    _SUBVERB_ADD: "vault_access_add",
    _SUBVERB_REMOVE: "vault_access_remove",
    _SUBVERB_LIST: "vault_access_list",
}


class CmdVault(DispatchCommand):
    """Manage a vault's access list.

    Usage:
      vault status
      vault access list
      vault access add <persona>
      vault access add/org <organization>
      vault access remove <persona>
      vault access remove/org <organization>
    """

    key = "vault"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``vault`` shows status."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _SUBVERB_STATUS:
            self._show_status()
            return
        parts = raw.split(maxsplit=1)
        verb = parts[0].lower()
        if verb != _SUBVERB_ACCESS:
            self.msg("Usage: vault <status|access ...>")
            return
        _MIN_ACCESS_PARTS = 2
        if len(parts) < _MIN_ACCESS_PARTS:
            self.msg("Usage: vault access <list|add|remove> ...")
            return
        sub_parts = parts[1].split(maxsplit=1)
        self._subverb = sub_parts[0].lower()
        self._rest = sub_parts[1].strip() if len(sub_parts) > 1 else ""
        if self._subverb == _SUBVERB_LIST:
            self._rest = ""
            super().func()
            return
        if self._subverb not in _ACCESS_SUBVERBS:
            self.msg("Usage: vault access <list|add|remove> ...")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key=_ACCESS_SUBVERBS[self._subverb],
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _SUBVERB_LIST:
            return {}
        if self._subverb == _SUBVERB_ADD:
            return self._args_add_remove()
        if self._subverb == _SUBVERB_REMOVE:
            return self._args_add_remove()
        return {}  # unreachable — func() gates on _ACCESS_SUBVERBS

    # -- resolution helpers -----------------------------------------------

    def _args_add_remove(self) -> dict[str, Any]:
        """Resolve add/remove args: ``<persona>`` or ``/org <organization>``."""
        if not self._rest:
            msg = "Specify a persona or organization name."
            raise CommandError(msg)
        if self._rest.startswith(_PREFIX_ORG + " "):
            org_name = self._rest[len(_PREFIX_ORG) + 1 :].strip()
            if not org_name:
                msg = "Specify an organization name."
                raise CommandError(msg)
            from world.societies.models import Organization  # noqa: PLC0415

            org = Organization.objects.filter(name__iexact=org_name).first()
            if org is None:
                msg = f"No organization named '{org_name}' was found."
                raise CommandError(msg)
            return {"holder_organization": org}
        persona_name = self._rest
        from world.scenes.models import Persona  # noqa: PLC0415

        persona = Persona.objects.filter(name__iexact=persona_name).first()
        if persona is None:
            msg = f"No persona named '{persona_name}' was found."
            raise CommandError(msg)
        return {"holder_persona": persona}

    # -- status (read-only, no dispatch) ----------------------------------

    def _show_status(self) -> None:
        """Show the vault's level, capacity, and founder."""
        from world.room_features.vault_services import (  # noqa: PLC0415
            vault_capacity_remaining,
            vault_for_location,
        )

        vault = vault_for_location(self.caller.location)
        if vault is None:
            self.msg("There is no vault here.")
            return
        remaining = vault_capacity_remaining(vault)
        instance = vault.feature_instance
        self.msg(
            f"Vault (Level {instance.level}): "
            f"{vault.max_items - remaining}/{vault.max_items} items. "
            f"Founder: {vault.founder_persona}."
        )
