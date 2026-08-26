"""Org-vault bank actions (#2540 Layer 4) — the WHERE gate on vault custody.

Deposit/withdraw are performable only where a **BANK** room feature stands (a bank
room on grid, or an owner-installed bank-access decor feature — Apostate's ratified
access surface). The actions are thin over the audited ``world.items`` vault
services; custody never depends on the room, only reachability does.

CONTROLLER RULING (#2540): the same access surface covers the org's "bank account"
too — ``TreasuryWithdrawAction`` reuses the identical ``_at_bank`` gate to draw
coppers from the org treasury, not just items from the vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_NOT_AT_BANK = "There is no bank access here."
_MSG_NO_ORGANIZATION = "No such organization."
_MSG_NO_ITEM = "No such item."
_MSG_INVALID_AMOUNT = "amount must be a positive whole number."


def _resolve_active_persona(actor: ObjectDB) -> Any:
    """Return the actor's active persona, or ``None`` if unavailable."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _at_bank(actor: ObjectDB) -> bool:
    """True when the actor's room carries an active BANK feature (the LAB pattern)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    location = actor.location
    if location is None:
        return False
    try:
        room_profile = location.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return False
    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.BANK,
        )
        .active()
        .exists()
    )


def _resolve_organization(organization_id: Any) -> Any:
    from world.societies.models import Organization  # noqa: PLC0415

    if isinstance(organization_id, Organization):
        return organization_id
    return Organization.objects.filter(pk=organization_id).first()


def _resolve_item(item_instance_id: Any) -> Any:
    from world.items.models import ItemInstance  # noqa: PLC0415

    if isinstance(item_instance_id, ItemInstance):
        return item_instance_id
    return ItemInstance.objects.filter(pk=item_instance_id).first()


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or ``None`` if it isn't one.

    Fails loud (returns None -> caller refuses) rather than silently coercing a
    negative/zero/missing amount to something valid. Mirrors
    ``gm_adjudication._coerce_positive_int``.
    """
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _bank_org_context(actor: ObjectDB, kwargs: dict[str, Any]) -> tuple[Any, Any]:
    """Resolve (persona, organization) at a bank, or a failure ActionResult in slot 0.

    The item-free half of ``_bank_context`` — active persona + the ``_at_bank`` WHERE
    gate + org resolution, with no item involved. Shared by every bank-gated action:
    the vault item actions build on it via ``_BankAction._bank_context``, and
    ``TreasuryWithdrawAction`` (coin, no item) uses it directly.
    """
    persona = _resolve_active_persona(actor)
    if persona is None:
        return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER), None
    if not _at_bank(actor):
        return ActionResult(success=False, message=_MSG_NOT_AT_BANK), None
    organization = _resolve_organization(kwargs.get("organization_id"))
    if organization is None:
        return ActionResult(success=False, message=_MSG_NO_ORGANIZATION), None
    return persona, organization


@dataclass
class _BankAction(Action):
    """Shared shape: active persona + bank-room gate + org/item resolution."""

    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def _bank_context(self, actor: ObjectDB, kwargs: dict[str, Any]) -> tuple[Any, Any, Any]:
        """Resolve (persona, organization, item) or a failure ActionResult in slot 0."""
        persona, organization = _bank_org_context(actor, kwargs)
        if isinstance(persona, ActionResult):
            return persona, None, None
        item = _resolve_item(kwargs.get("item_instance_id"))
        if item is None:
            return ActionResult(success=False, message=_MSG_NO_ITEM), None, None
        return persona, organization, item


@dataclass
class VaultDepositAction(_BankAction):
    key: str = "vault_deposit"
    name: str = "Deposit to Vault"
    icon: str = "vault"
    description: str = "Place an item you hold into your organization's vault."

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.items.services.org_vault import deposit_item_to_vault  # noqa: PLC0415

        persona, organization, item = self._bank_context(actor, kwargs)
        if isinstance(persona, ActionResult):
            return persona
        try:
            deposit_item_to_vault(organization=organization, persona=persona, item_instance=item)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        return ActionResult(success=True, message=f"{item} is now in {organization.name}'s vault.")


@dataclass
class VaultWithdrawAction(_BankAction):
    key: str = "vault_withdraw"
    name: str = "Withdraw from Vault"
    icon: str = "vault"
    description: str = "Draw an item from your organization's vault (rank-gated)."

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.items.services.org_vault import withdraw_item_from_vault  # noqa: PLC0415

        persona, organization, item = self._bank_context(actor, kwargs)
        if isinstance(persona, ActionResult):
            return persona
        try:
            withdraw_item_from_vault(organization=organization, persona=persona, item_instance=item)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        return ActionResult(
            success=True, message=f"You draw {item} from {organization.name}'s vault."
        )


@dataclass
class TreasuryWithdrawAction(_BankAction):
    """Draw coppers from an organization's treasury into the actor's purse.

    CONTROLLER RULING (#2540): treasury withdrawal is bank-gated with the same
    ``_at_bank`` prerequisite as the vault item actions — the ratified Layer 4 access
    surface covers the org's "bank account" (coin) as well as the vault (items).
    Skips item resolution entirely (``_bank_org_context``, not ``_bank_context``);
    the rank gate itself is enforced by the service (``can_spend_treasury``), not
    here.
    """

    key: str = "treasury_withdraw"
    name: str = "Withdraw from Treasury"
    icon: str = "vault"
    description: str = (
        "Draw coppers from your organization's treasury into your purse (rank-gated)."
    )

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.currency.constants import format_coppers  # noqa: PLC0415
        from world.currency.services import withdraw_from_treasury  # noqa: PLC0415

        persona, organization = _bank_org_context(actor, kwargs)
        if isinstance(persona, ActionResult):
            return persona
        amount = _coerce_positive_int(kwargs.get("amount"))
        if amount is None:
            return ActionResult(success=False, message=_MSG_INVALID_AMOUNT)
        try:
            withdraw_from_treasury(organization=organization, persona=persona, amount=amount)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        return ActionResult(
            success=True,
            message=f"You draw {format_coppers(amount)} from {organization.name}'s treasury.",
        )


# Module-level singletons — registered in actions/registry.py
vault_deposit = VaultDepositAction()
vault_withdraw = VaultWithdrawAction()
treasury_withdraw = TreasuryWithdrawAction()
