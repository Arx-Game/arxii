"""Trade models (#2990): two-sided negotiated exchange between co-located characters.

Mirrors ``world.items.market``'s shape (per ADR-0017: a new subsystem is a
submodule of an existing app) but solves a different problem — negotiation,
not posted-price buy-now. A ``TradeSession`` is CharacterSheet-keyed (the
body owns items, #684 — see ``ItemInstance.holder_character_sheet``), not
Persona-keyed, and moves through PROPOSED -> ACTIVE -> COMPLETED/CANCELLED.
``TradeItemStake`` rows declare which items are on the table per side; plain
coin columns on the session cover coin (no list needed — one scalar per
side). See ``world.items.trade.services`` for the full state machine and the
atomic ``execute_trade`` swap (mirrors ``resolve_crossing_offer``'s
two-phase ``select_for_update`` pattern).
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

_CHARACTER_SHEET_FK = "arxii.CharacterSheet"
_INSTANCE_FK = "arxii.ItemInstance"


class TradeSession(SharedMemoryModel):
    """A negotiated trade between two co-located characters (#2990).

    No DB-level "one open session per pair" constraint — a symmetric-pair
    partial unique index needs canonical ordering and buys little;
    ``propose_trade`` checks for an existing open session either direction
    inside its own ``transaction.atomic()`` instead.
    """

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    initiator_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="trade_sessions_initiated",
        help_text="The character who proposed the trade.",
    )
    counterparty_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="trade_sessions_received",
        help_text="The character invited to the trade.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROPOSED,
    )
    initiator_confirmed = models.BooleanField(default=False)
    counterparty_confirmed = models.BooleanField(default=False)
    initiator_coppers = models.PositiveIntegerField(
        default=0,
        help_text="Coin the initiator has staged onto the table.",
    )
    counterparty_coppers = models.PositiveIntegerField(
        default=0,
        help_text="Coin the counterparty has staged onto the table.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session reached COMPLETED or CANCELLED.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["initiator_sheet", "status"]),
            models.Index(fields=["counterparty_sheet", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"Trade #{self.pk}: {self.initiator_sheet} <-> "
            f"{self.counterparty_sheet} ({self.status})"
        )

    def other_sheet_id(self, sheet_id: int) -> int:
        """Return the other party's sheet pk given one side's pk.

        Raises ``ValueError`` if ``sheet_id`` is neither party — callers use
        this only after already confirming membership, so this is a
        programmer-error guard, not a player-facing validation.
        """
        if sheet_id == self.initiator_sheet_id:
            return self.counterparty_sheet_id
        if sheet_id == self.counterparty_sheet_id:
            return self.initiator_sheet_id
        msg = f"Sheet {sheet_id} is not a party to trade #{self.pk}."
        raise ValueError(msg)


class TradeItemStake(SharedMemoryModel):
    """One item a party has put on the table in a ``TradeSession`` (#2990).

    No DB constraint blocking the same item staked in two sessions at once
    (can't express "no other open session" across a join in a
    ``UniqueConstraint``) — ``stake_item`` re-verifies possession under
    ``select_for_update`` at stake time, and ``execute_trade`` re-verifies
    again at execute time.
    """

    session = models.ForeignKey(
        TradeSession,
        on_delete=models.CASCADE,
        related_name="item_stakes",
    )
    offered_by_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="trade_stakes",
        help_text="Must equal session.initiator_sheet or session.counterparty_sheet.",
    )
    item_instance = models.ForeignKey(
        _INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="trade_stakes",
    )
    staked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["staked_at"]
        indexes = [models.Index(fields=["session"])]

    def __str__(self) -> str:
        return f"{self.item_instance} staked by {self.offered_by_sheet} in trade #{self.session_id}"
