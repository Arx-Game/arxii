"""Typed exceptions for player<->player negotiated trade (#2990).

Per CLAUDE.md `ViewSet & API Design`: typed exceptions with `user_message`
property + `SAFE_MESSAGES` allowlist for safe API surfacing. Action and view
layers read `exc.user_message` — never `str(exc)`.

Possession, adjacency, and hot-goods-consent failures reuse the existing
`world.items.exceptions` family (`NotInPossession`, `RecipientNotAdjacent`,
`RecipientConsentDenied`) rather than minting trade-specific duplicates —
those refusals mean exactly the same thing here as they do for a plain
`give()`. Session-not-found uses `TradeSession.DoesNotExist` directly at the
action layer (the `outfit_id` precedent — `actions/definitions/outfits.py`),
not a typed wrapper. Only trade-shaped refusals get a new class here.
"""

from typing import ClassVar


class TradeError(Exception):
    """Base for trade typed exceptions."""

    user_message: str = "That trade action could not be completed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That trade action could not be completed."},
    )


class SelfTradeNotAllowed(TradeError):
    """Raised when a character tries to propose a trade with themselves."""

    user_message = "You cannot trade with yourself."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You cannot trade with yourself."})


class TradeSessionOpenAlready(TradeError):
    """Raised when the pair already has an open (PROPOSED/ACTIVE) session (#2990)."""

    user_message = "You already have an open trade with them."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You already have an open trade with them."},
    )


class NotATradeParty(TradeError):
    """Raised when the acting character is neither side of the trade session."""

    user_message = "You are not part of that trade."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You are not part of that trade."})


class TradeNotProposed(TradeError):
    """Raised when ``accept_trade`` targets a session not in PROPOSED."""

    user_message = "That trade has already been accepted or closed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That trade has already been accepted or closed."},
    )


class TradeNotActive(TradeError):
    """Raised when an ACTIVE-only action (stage/unstage/set coin/confirm) hits a
    session that is not ACTIVE (still PROPOSED, or already resolved).
    """

    user_message = "That trade is not open for staging right now."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That trade is not open for staging right now."},
    )


class TradeAlreadyResolved(TradeError):
    """Raised when ``cancel_trade`` targets a session already COMPLETED/CANCELLED."""

    user_message = "That trade is already closed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That trade is already closed."})


class TradeItemAlreadyStaked(TradeError):
    """Raised when an item is already staked in this (or another open) session."""

    user_message = "That item is already staked in a trade."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That item is already staked in a trade."},
    )


class TradeStakeNotFound(TradeError):
    """Raised when ``unstake_item`` is called with a stake that doesn't exist."""

    user_message = "That item is not on the table."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That item is not on the table."})


class TradeCoinOverBalance(TradeError):
    """Raised when ``set_coin_offer`` stages more coin than the party's purse holds.

    A soft check at stage time — ``transfer()``'s own balance check inside
    ``execute_trade`` is the hard guard that always wins.
    """

    user_message = "You don't have that much coin."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You don't have that much coin."})


class TradeItemUnavailable(TradeError):
    """An item staked in the session is no longer in the staking party's possession
    at execute time (moved, destroyed, vaulted, or given away mid-negotiation).

    The whole trade aborts — session stays ACTIVE, both confirms reset to
    False — so the action layer can tell the UI which stake failed.
    """

    user_message = "One of the staged items is no longer available; the trade was not completed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"One of the staged items is no longer available; the trade was not completed."},
    )

    def __init__(self, stake_id: int | None = None) -> None:
        self.stake_id = stake_id
        super().__init__(self.user_message)
