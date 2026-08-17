"""Player<->player negotiated trade actions (#2990).

Thin action/service-function pairs per the action-centric architecture: each
action owns its prerequisite checks (adjacency, session/stake membership) and
calls the matching ``world.items.trade.services`` function for the mutation
— same shape as ``GiveAction``/``GiveCoinsAction``. Staging/confirming stay
quiet (no room broadcast — every drag-and-drop UI edit narrating would be
spammy); propose/accept/cancel and a completed trade narrate to the room,
since those are the dramatic beats worth seeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.item_helpers import resolve_item_instance
from actions.prerequisites import resolve_actor_sheet
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from world.items.exceptions import (
    NotInPossession,
    RecipientConsentDenied,
    RecipientNotAdjacent,
)
from world.items.trade.exceptions import (
    NotATradeParty,
    TradeAlreadyResolved,
    TradeCoinOverBalance,
    TradeError,
    TradeItemAlreadyStaked,
    TradeItemUnavailable,
    TradeNotActive,
    TradeNotProposed,
)
from world.items.trade.models import TradeItemStake, TradeSession
from world.items.trade.services import (
    accept_trade,
    cancel_trade,
    confirm,
    propose_trade,
    set_coin_offer,
    stake_item,
    unstake_item,
)

_NO_SHEET_MESSAGE = "You have no character sheet."
_NO_TRADE_MESSAGE = "That trade no longer exists."


def _amount_kwarg(kwargs: dict[str, Any]) -> int | None:
    """Return the ``amount`` kwarg if it's a non-negative int, else ``None``.

    Unlike ``_positive_amount`` (currency actions), 0 is valid here — it's
    how a party clears a coin offer they already staged.
    """
    amount = kwargs.get("amount")
    if isinstance(amount, int) and amount >= 0:
        return amount
    return None


def _fetch_session(kwargs: dict[str, Any]) -> TradeSession | None:
    session_id = kwargs.get("session_id")
    if session_id is None:
        return None
    return TradeSession.objects.filter(pk=session_id).first()


def _resolve_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the ``target`` kwarg from either dispatch shape.

    Telnet passes an already-resolved ``ObjectDB``. REST dispatch
    (``dispatch_player_action`` -> ``_dispatch_registry``) does no ``ObjectDB``
    resolution of its own and ``objectdb_target_kwargs`` only helps the
    websocket inputfunc — so the web trade panel's POST sends a raw pk
    (``int``). Resolve defensively here, mirroring ``_resolve_look_target``
    (``actions/definitions/perception.py``).
    """
    target = kwargs.get("target")
    if target is None or isinstance(target, ObjectDB):
        return target
    return ObjectDB.objects.filter(pk=target).first()


@dataclass
class ProposeTradeAction(Action):
    """Open a negotiated trade with a co-located character."""

    key: str = "propose_trade"
    name: str = "Propose Trade"
    icon: str = "handshake"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = _resolve_target(kwargs)
        if target is None:
            return ActionResult(success=False, message="Propose a trade with whom?")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)
        target_sheet = resolve_actor_sheet(target)
        if target_sheet is None:
            return ActionResult(success=False, message="They can't trade.")

        try:
            session = propose_trade(actor_sheet, target_sheet)
        except TradeError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except RecipientNotAdjacent as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        target_state = sdm.initialize_state_for_object(target)
        message_location(
            actor_state,
            "$You() $conj(offer) to trade with {target}.",
            target=target_state,
            mapping={"target": target_state},
        )
        return ActionResult(success=True, data={"session_id": session.pk})


@dataclass
class AcceptTradeAction(Action):
    """Accept a proposed trade, opening it up for staging."""

    key: str = "accept_trade"
    name: str = "Accept Trade"
    icon: str = "handshake"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        session = _fetch_session(kwargs)
        if session is None:
            return ActionResult(success=False, message=_NO_TRADE_MESSAGE)

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            accept_trade(session, actor_sheet)
        except (NotATradeParty, TradeNotProposed) as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        other = session.initiator_sheet.character
        other_state = sdm.initialize_state_for_object(other)
        message_location(
            actor_state,
            "$You() $conj(accept) {other}'s trade offer.",
            target=other_state,
            mapping={"other": other_state},
        )
        return ActionResult(success=True, data={"session_id": session.pk})


@dataclass
class StageTradeItemAction(Action):
    """Put an item on the table in an active trade session."""

    key: str = "stage_trade_item"
    name: str = "Stage Trade Item"
    icon: str = "handshake"
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
        session = _fetch_session(kwargs)
        if session is None:
            return ActionResult(success=False, message=_NO_TRADE_MESSAGE)

        target = _resolve_target(kwargs)
        item_instance = resolve_item_instance(target) if target is not None else None
        if item_instance is None:
            return ActionResult(success=False, message="Stage what?")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            stake = stake_item(session, actor_sheet, item_instance)
        except (
            TradeNotActive,
            NotATradeParty,
            NotInPossession,
            TradeItemAlreadyStaked,
            RecipientConsentDenied,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, data={"stake_id": stake.pk})


@dataclass
class UnstageTradeItemAction(Action):
    """Pull a staged item back off the table."""

    key: str = "unstage_trade_item"
    name: str = "Unstage Trade Item"
    icon: str = "handshake"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        stake_id = kwargs.get("stake_id")
        stake = TradeItemStake.objects.filter(pk=stake_id).first() if stake_id is not None else None
        if stake is None:
            return ActionResult(success=False, message="That item is not on the table.")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)
        if stake.offered_by_sheet_id != actor_sheet.pk:
            return ActionResult(success=False, message="That's not yours to unstage.")

        try:
            unstake_item(stake)
        except TradeNotActive as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True)


@dataclass
class SetTradeCoinAction(Action):
    """Set the coin offered in an active trade session."""

    key: str = "set_trade_coin"
    name: str = "Set Trade Coin"
    icon: str = "coins"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        session = _fetch_session(kwargs)
        if session is None:
            return ActionResult(success=False, message=_NO_TRADE_MESSAGE)
        amount = _amount_kwarg(kwargs)
        if amount is None:
            return ActionResult(success=False, message="Offer how much coin?")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            set_coin_offer(session, actor_sheet, amount)
        except (TradeNotActive, NotATradeParty, TradeCoinOverBalance) as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))

        return ActionResult(success=True)


@dataclass
class ConfirmTradeAction(Action):
    """Confirm the current offer; executes the swap once both sides confirm."""

    key: str = "confirm_trade"
    name: str = "Confirm Trade"
    icon: str = "handshake"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        session = _fetch_session(kwargs)
        if session is None:
            return ActionResult(success=False, message=_NO_TRADE_MESSAGE)

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            session = confirm(session, actor_sheet)
        except (TradeNotActive, NotATradeParty, TradeItemUnavailable, RecipientNotAdjacent) as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))

        if session.status == TradeSession.Status.COMPLETED:
            sdm = context.scene_data if context else SceneDataManager()
            actor_state = sdm.initialize_state_for_object(actor)
            other_obj = (
                session.counterparty_sheet.character
                if session.initiator_sheet_id == actor_sheet.pk
                else session.initiator_sheet.character
            )
            other_state = sdm.initialize_state_for_object(other_obj)
            message_location(
                actor_state,
                "$You() and {other} complete a trade.",
                target=other_state,
                mapping={"other": other_state},
            )
            return ActionResult(success=True, data={"session_id": session.pk, "completed": True})

        return ActionResult(
            success=True,
            message="Confirmed. Waiting on the other side.",
            data={"session_id": session.pk, "completed": False},
        )


@dataclass
class CancelTradeAction(Action):
    """Cancel a trade session — either party, any time before it completes."""

    key: str = "cancel_trade"
    name: str = "Cancel Trade"
    icon: str = "handshake"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        session = _fetch_session(kwargs)
        if session is None:
            return ActionResult(success=False, message=_NO_TRADE_MESSAGE)

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        try:
            cancel_trade(session, actor_sheet)
        except (NotATradeParty, TradeAlreadyResolved) as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        other_obj = (
            session.counterparty_sheet.character
            if session.initiator_sheet_id == actor_sheet.pk
            else session.initiator_sheet.character
        )
        other_state = sdm.initialize_state_for_object(other_obj)
        message_location(
            actor_state,
            "$You() $conj(call) off the trade with {other}.",
            target=other_state,
            mapping={"other": other_state},
        )
        return ActionResult(success=True)
