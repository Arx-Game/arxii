"""Physical-currency actions (#1909): withdraw/deposit loose cash, give coins.

Coppers move through ``world.currency.services.transfer`` (the audited ledger
path); these actions are the physical-cash face of it — pulling money out of
the ledger into a carriable loose-coin cache, redeeming any coin item back
into the ledger, and handing coins directly to another character.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.item_helpers import resolve_item_instance
from actions.prerequisites import resolve_actor_sheet
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from world.currency.constants import format_coppers
from world.currency.services import (
    get_or_create_purse,
    mint_loose_cache,
    redeem_instrument,
    transfer,
)
from world.items.exceptions import RecipientNotAdjacent

_NO_SHEET_MESSAGE = "You have no character sheet."


def _positive_amount(kwargs: dict[str, Any]) -> int | None:
    """Return the ``amount`` kwarg if it's a positive int, else ``None``."""
    amount = kwargs.get("amount")
    if isinstance(amount, int) and amount > 0:
        return amount
    return None


@dataclass
class WithdrawCoinsAction(Action):
    """Pull coppers out of your purse as a carriable loose-coin cache (#1909)."""

    key: str = "withdraw_coins"
    name: str = "Withdraw Coins"
    icon: str = "coins"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        amount = _positive_amount(kwargs)
        if amount is None:
            return ActionResult(success=False, message="Withdraw how much?")

        sheet = resolve_actor_sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            mint_loose_cache(
                amount=amount,
                holder_sheet=sheet,
                from_purse=get_or_create_purse(sheet),
            )
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            "$You() $conj(withdraw) {amount} in loose coins.",
            mapping={"amount": format_coppers(amount)},
        )
        return ActionResult(success=True)


@dataclass
class DepositCoinsAction(Action):
    """Redeem a physical coin item back into your purse (#1909).

    Works for any instrument — a loose-coin cache or one of the six grand
    coins alike; deposit is redemption regardless of denomination.
    """

    key: str = "deposit_coins"
    name: str = "Deposit Coins"
    icon: str = "coins"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Deposit what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be deposited.")

        sheet = resolve_actor_sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            details = item_instance.currency_instrument
        except ObjectDoesNotExist:
            return ActionResult(success=False, message="That isn't your coin.")
        if item_instance.holder_character_sheet_id != sheet.pk:
            return ActionResult(success=False, message="That isn't your coin.")

        face_value = details.face_value
        redeem_instrument(instance=item_instance, to_purse=get_or_create_purse(sheet))

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            "$You() $conj(deposit) coins worth {amount}.",
            mapping={"amount": format_coppers(face_value)},
        )
        return ActionResult(success=True)


@dataclass
class GiveCoinsAction(Action):
    """Hand coppers directly to a co-located character's purse (#1909).

    Telnet's ``give <amount> to <recipient>`` and the web give-flow swap to
    this action (instead of ``GiveAction``) when the item-name text parses as
    money — see ``CmdGive.resolve_action_args``.
    """

    key: str = "give_coins"
    name: str = "Give Coins"
    icon: str = "coins"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"recipient"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        recipient = kwargs.get("recipient")
        amount = _positive_amount(kwargs)
        if recipient is None or amount is None:
            return ActionResult(success=False, message="Give how much to whom?")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)
        recipient_sheet = resolve_actor_sheet(recipient)
        if recipient_sheet is None:
            return ActionResult(success=False, message="They can't hold money.")

        if recipient.location != actor.location:
            return ActionResult(success=False, message=RecipientNotAdjacent.user_message)

        try:
            transfer(
                amount=amount,
                reason="give coins",
                from_purse=get_or_create_purse(actor_sheet),
                to_purse=get_or_create_purse(recipient_sheet),
            )
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        recipient_state = sdm.initialize_state_for_object(recipient)
        message_location(
            actor_state,
            "$You() $conj(give) {recipient} {amount}.",
            target=recipient_state,
            mapping={
                "recipient": recipient_state,
                "amount": format_coppers(amount),
            },
        )
        return ActionResult(success=True)
