"""Vault access-list management actions (#2179).

All three are REGISTRY actions, ``target_type=SELF``, ``category="items"``.
Owner-gated via ``can_modify_room_features``. The vault is resolved from
the actor's current room location.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.types import ActionCategory, ActionResult, TargetType

_MSG_NO_ACTIVE_CHARACTER = "You have no active character."
_MSG_NO_VAULT = "There is no vault here."
_MSG_NOT_CONTROL = "You do not control this vault."


def _resolve_active_persona(actor: ObjectDB) -> Any:
    """Resolve the actor's active persona, or None for sheet-less actors."""
    try:
        sheet = actor.sheet_data
    except AttributeError:
        return None
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        return sheet.active_persona or sheet.primary_persona
    except Persona.DoesNotExist:
        return None


@dataclass
class VaultAccessAddAction(Action):
    """Add a persona or organization to the vault's access list (#2179)."""

    key: str = "vault_access_add"
    name: str = "Grant Vault Access"
    icon: str = "key"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415
        from world.room_features.vault_services import (  # noqa: PLC0415
            add_vault_access,
            vault_for_location,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        vault = vault_for_location(actor.location)
        if vault is None:
            return ActionResult(success=False, message=_MSG_NO_VAULT)

        if not can_modify_room_features(persona, actor.location):
            return ActionResult(success=False, message=_MSG_NOT_CONTROL)

        holder_persona = kwargs.get("holder_persona")
        holder_organization = kwargs.get("holder_organization")
        if holder_persona is None and holder_organization is None:
            _msg = "Specify a persona or organization to add."
            return ActionResult(success=False, message=_msg)

        try:
            add_vault_access(
                vault,
                holder_persona=holder_persona,
                holder_organization=holder_organization,
                added_by=persona,
            )
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = str(holder_persona) if holder_persona else str(holder_organization)
        return ActionResult(success=True, message=f"Access granted to {target_name}.")


@dataclass
class VaultAccessRemoveAction(Action):
    """Remove a persona or organization from the vault's access list (#2179)."""

    key: str = "vault_access_remove"
    name: str = "Revoke Vault Access"
    icon: str = "key-off"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415
        from world.room_features.vault_services import (  # noqa: PLC0415
            remove_vault_access,
            vault_for_location,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        vault = vault_for_location(actor.location)
        if vault is None:
            return ActionResult(success=False, message=_MSG_NO_VAULT)

        if not can_modify_room_features(persona, actor.location):
            return ActionResult(success=False, message=_MSG_NOT_CONTROL)

        holder_persona = kwargs.get("holder_persona")
        holder_organization = kwargs.get("holder_organization")
        if holder_persona is None and holder_organization is None:
            _msg = "Specify a persona or organization to remove."
            return ActionResult(success=False, message=_msg)

        count = remove_vault_access(
            vault,
            holder_persona=holder_persona,
            holder_organization=holder_organization,
        )
        if count == 0:
            _msg = "That persona or organization was not on the access list."
            return ActionResult(success=False, message=_msg)

        target_name = str(holder_persona) if holder_persona else str(holder_organization)
        return ActionResult(success=True, message=f"Access revoked from {target_name}.")


@dataclass
class VaultAccessListAction(Action):
    """List the vault's access entries (#2179)."""

    key: str = "vault_access_list"
    name: str = "List Vault Access"
    icon: str = "list"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415
        from world.room_features.vault_services import (  # noqa: PLC0415
            list_vault_access,
            vault_for_location,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        vault = vault_for_location(actor.location)
        if vault is None:
            return ActionResult(success=False, message=_MSG_NO_VAULT)

        if not can_modify_room_features(persona, actor.location):
            return ActionResult(success=False, message=_MSG_NOT_CONTROL)

        entries = list_vault_access(vault)
        return ActionResult(
            success=True,
            message=f"Vault access list ({len(entries)} entries):",
            data={"entries": entries, "founder": vault.founder_persona},
        )
