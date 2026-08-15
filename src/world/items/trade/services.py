"""Trade services (#2990): the negotiated player<->player exchange state machine.

``execute_trade`` mirrors ``resolve_crossing_offer``'s (``world.magic.services.crossing``)
two-phase ``select_for_update`` shape: re-lock the session row and every staked item
before committing to the swap, so an item that moved (given away, destroyed, vaulted)
or a purse that emptied between staging and execute is caught atomically — the whole
trade aborts rather than partially completing. Item relocation mirrors
``flows.service_functions.inventory.give()``'s shape (unequip if worn, ``move_to``,
reassign ``holder_character_sheet``, write an ``OwnershipEvent``); coin movement routes
through ``world.currency.services.transfer`` (the single mutation point for all money).

Barter falls out for free: both sides can stake items *and* coin in the same session —
nothing here distinguishes "barter" as a separate mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from world.items.constants import OwnershipEventType
from world.items.exceptions import NotInPossession, RecipientNotAdjacent
from world.items.models import ItemInstance, OwnershipEvent
from world.items.trade.exceptions import (
    NotATradeParty,
    SelfTradeNotAllowed,
    TradeAlreadyResolved,
    TradeCoinOverBalance,
    TradeItemAlreadyStaked,
    TradeItemUnavailable,
    TradeNotActive,
    TradeNotProposed,
    TradeSessionOpenAlready,
)
from world.items.trade.models import TradeItemStake, TradeSession

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# Exceptions that mean "the swap did not go through" — execute_trade resets both
# confirms (outside the rolled-back transaction) so the pair can renegotiate and
# re-confirm instead of being stuck on a stale "both confirmed" ACTIVE session.
# TradeNotActive is deliberately excluded: it fires when the session already moved
# to a terminal/inconsistent state (e.g. a racing confirm already executed it, or
# a concurrent unstake already reset the flags) — nothing to reset there.
_ABORT_RESETS_CONFIRMS: tuple[type[Exception], ...] = (
    TradeItemUnavailable,
    RecipientNotAdjacent,
    ValidationError,
)


def _other_party_sheet(session: TradeSession, party_sheet: CharacterSheet) -> CharacterSheet:
    """Return the other side of ``session``, raising if ``party_sheet`` isn't a party."""
    if party_sheet.pk == session.initiator_sheet_id:
        return session.counterparty_sheet
    if party_sheet.pk == session.counterparty_sheet_id:
        return session.initiator_sheet
    raise NotATradeParty


def _reset_confirms(session: TradeSession) -> None:
    session.initiator_confirmed = False
    session.counterparty_confirmed = False
    session.save(update_fields=["initiator_confirmed", "counterparty_confirmed"])


def propose_trade(
    initiator_sheet: CharacterSheet, counterparty_sheet: CharacterSheet
) -> TradeSession:
    """Open a ``PROPOSED`` trade session between two co-located characters.

    Neither side may stage anything until ``accept_trade`` moves the session
    to ``ACTIVE`` — nobody gets items shoved at them by a target who never
    agreed to negotiate.
    """
    if initiator_sheet.pk == counterparty_sheet.pk:
        raise SelfTradeNotAllowed
    if initiator_sheet.character.location != counterparty_sheet.character.location:
        raise RecipientNotAdjacent

    with transaction.atomic():
        open_exists = (
            TradeSession.objects.filter(
                status__in=[TradeSession.Status.PROPOSED, TradeSession.Status.ACTIVE],
            )
            .filter(
                models.Q(initiator_sheet=initiator_sheet, counterparty_sheet=counterparty_sheet)
                | models.Q(initiator_sheet=counterparty_sheet, counterparty_sheet=initiator_sheet),
            )
            .exists()
        )
        if open_exists:
            raise TradeSessionOpenAlready
        return TradeSession.objects.create(
            initiator_sheet=initiator_sheet,
            counterparty_sheet=counterparty_sheet,
        )


def accept_trade(session: TradeSession, counterparty_sheet: CharacterSheet) -> TradeSession:
    """The invited party accepts: ``PROPOSED`` -> ``ACTIVE``."""
    if counterparty_sheet.pk != session.counterparty_sheet_id:
        raise NotATradeParty
    if session.status != TradeSession.Status.PROPOSED:
        raise TradeNotProposed
    session.status = TradeSession.Status.ACTIVE
    session.save(update_fields=["status"])
    return session


def stake_item(
    session: TradeSession, party_sheet: CharacterSheet, item_instance: ItemInstance
) -> TradeItemStake:
    """Put ``item_instance`` on the table for ``party_sheet``. Resets both confirms.

    Re-verifies possession under ``select_for_update`` (belt-and-suspenders with
    ``execute_trade``'s own re-check), refuses a double-stake (this session or any
    other open one — no DB constraint can express that join), and runs the same
    hot-goods consent gate ``give()`` uses so a hot item can't launder through a
    trade any easier than through a plain give.
    """
    if session.status != TradeSession.Status.ACTIVE:
        raise TradeNotActive
    other_sheet = _other_party_sheet(session, party_sheet)

    with transaction.atomic():
        locked_item = ItemInstance.objects.select_for_update().filter(pk=item_instance.pk).first()
        if locked_item is None or locked_item.holder_character_sheet_id != party_sheet.pk:
            raise NotInPossession
        already_staked = TradeItemStake.objects.filter(
            item_instance=locked_item,
            session__status__in=[TradeSession.Status.PROPOSED, TradeSession.Status.ACTIVE],
        ).exists()
        if already_staked:
            raise TradeItemAlreadyStaked

        from flows.service_functions.inventory import (  # noqa: PLC0415
            require_hot_goods_consent,
        )

        require_hot_goods_consent(other_sheet, locked_item)

        stake = TradeItemStake.objects.create(
            session=session,
            offered_by_sheet=party_sheet,
            item_instance=locked_item,
        )
        _reset_confirms(session)
    return stake


def unstake_item(stake: TradeItemStake) -> TradeSession:
    """Pull a staked item back off the table. Resets both confirms.

    Authorization (only the staking party may unstake their own item) is the
    calling action's prerequisite check, same as the action-centric split
    elsewhere — this function trusts the ``stake`` it's handed.
    """
    session = stake.session
    if session.status != TradeSession.Status.ACTIVE:
        raise TradeNotActive
    with transaction.atomic():
        stake.delete()
        _reset_confirms(session)
    return session


def set_coin_offer(session: TradeSession, party_sheet: CharacterSheet, amount: int) -> TradeSession:
    """Set the coin ``party_sheet`` is offering. Resets both confirms.

    Soft-checks ``amount`` against the party's purse balance at stage time —
    ``transfer()``'s own balance check inside ``execute_trade`` is the hard,
    final guard (the purse can still be spent between staging and execute).
    """
    if session.status != TradeSession.Status.ACTIVE:
        raise TradeNotActive
    is_initiator = party_sheet.pk == session.initiator_sheet_id
    if not is_initiator and party_sheet.pk != session.counterparty_sheet_id:
        raise NotATradeParty
    if amount < 0:
        msg = "A coin offer cannot be negative."
        raise ValidationError(msg)

    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    purse = get_or_create_purse(party_sheet)
    if amount > purse.balance:
        raise TradeCoinOverBalance

    session.initiator_confirmed = False
    session.counterparty_confirmed = False
    if is_initiator:
        session.initiator_coppers = amount
        update_fields = ["initiator_coppers", "initiator_confirmed", "counterparty_confirmed"]
    else:
        session.counterparty_coppers = amount
        update_fields = ["counterparty_coppers", "initiator_confirmed", "counterparty_confirmed"]
    session.save(update_fields=update_fields)
    return session


def cancel_trade(session: TradeSession, party_sheet: CharacterSheet) -> TradeSession:
    """Either party cancels at any point before COMPLETED.

    Nothing to roll back — stakes are declarations, not escrow; nothing has
    moved until ``execute_trade`` runs.
    """
    _other_party_sheet(session, party_sheet)  # raises NotATradeParty if not a party
    if session.status not in (TradeSession.Status.PROPOSED, TradeSession.Status.ACTIVE):
        raise TradeAlreadyResolved
    session.status = TradeSession.Status.CANCELLED
    session.resolved_at = timezone.now()
    session.save(update_fields=["status", "resolved_at"])
    return session


def confirm(session: TradeSession, party_sheet: CharacterSheet) -> TradeSession:
    """Set ``party_sheet``'s confirm flag; execute the swap once both sides have."""
    if session.status != TradeSession.Status.ACTIVE:
        raise TradeNotActive
    is_initiator = party_sheet.pk == session.initiator_sheet_id
    if not is_initiator and party_sheet.pk != session.counterparty_sheet_id:
        raise NotATradeParty

    if is_initiator:
        session.initiator_confirmed = True
        session.save(update_fields=["initiator_confirmed"])
    else:
        session.counterparty_confirmed = True
        session.save(update_fields=["counterparty_confirmed"])

    session.refresh_from_db()
    if session.initiator_confirmed and session.counterparty_confirmed:
        try:
            execute_trade(session)
        except TradeNotActive:
            # A racing confirm() on the other side may have executed the trade
            # already (both saw "both confirmed" before either write landed).
            # If it went through, this is a no-op success, not a real failure.
            session.refresh_from_db()
            if session.status != TradeSession.Status.COMPLETED:
                raise
    return session


def _relocate_staked_item(
    item: ItemInstance, *, to_sheet: CharacterSheet, session: TradeSession
) -> None:
    """Move one staked item to the other party — mirrors ``give()``'s shape."""
    from world.items.services.equip import unequip_item  # noqa: PLC0415

    previous_holder_sheet = item.holder_character_sheet
    for equipped in list(item.equipped_slots.all()):
        unequip_item(equipped_item=equipped)

    if item.game_object is None or not item.game_object.move_to(to_sheet.character, quiet=True):
        raise TradeItemUnavailable

    item.holder_character_sheet = to_sheet
    item.save(update_fields=["holder_character_sheet"])

    giver_persona = (
        previous_holder_sheet.primary_persona if previous_holder_sheet is not None else None
    )
    OwnershipEvent.objects.create(
        item_instance=item,
        event_type=OwnershipEventType.TRANSFERRED,
        from_character_sheet=previous_holder_sheet,
        to_character_sheet=to_sheet,
        from_persona_display=giver_persona,
        to_persona_display=to_sheet.primary_persona,
        notes=f"trade #{session.pk}",
    )
    if previous_holder_sheet is not None:
        previous_holder_sheet.character.carried_items.invalidate()
    to_sheet.character.carried_items.invalidate()


def execute_trade(session: TradeSession) -> TradeSession:
    """Atomically swap every staked item and staged coin (#2990).

    Two-phase ``select_for_update`` shape mirroring ``resolve_crossing_offer``:
    re-lock the session row, re-verify ``ACTIVE`` + both confirms, then re-lock
    every staked item and re-verify it's still held by the party who staked it.
    Any mismatch aborts the *whole* trade — no partial swap. Everything from the
    session lock through the final status write is one ``transaction.atomic()``
    block, so there is no window where an item or coin left one side without
    landing on the other.
    """
    try:
        with transaction.atomic():
            locked_session = TradeSession.objects.select_for_update().filter(pk=session.pk).first()
            if (
                locked_session is None
                or locked_session.status != TradeSession.Status.ACTIVE
                or not locked_session.initiator_confirmed
                or not locked_session.counterparty_confirmed
            ):
                raise TradeNotActive

            if (
                locked_session.initiator_sheet.character.location
                != locked_session.counterparty_sheet.character.location
            ):
                raise RecipientNotAdjacent

            stakes = list(
                TradeItemStake.objects.filter(session=locked_session).select_related(
                    "offered_by_sheet",
                ),
            )
            locked_items = {
                item.pk: item
                for item in ItemInstance.objects.select_for_update().filter(
                    pk__in=[stake.item_instance_id for stake in stakes],
                )
            }
            for stake in stakes:
                item = locked_items.get(stake.item_instance_id)
                if item is None or item.holder_character_sheet_id != stake.offered_by_sheet_id:
                    raise TradeItemUnavailable(stake.pk)

            for stake in stakes:
                item = locked_items[stake.item_instance_id]
                to_sheet = (
                    locked_session.counterparty_sheet
                    if stake.offered_by_sheet_id == locked_session.initiator_sheet_id
                    else locked_session.initiator_sheet
                )
                _relocate_staked_item(item, to_sheet=to_sheet, session=locked_session)

            from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

            if locked_session.initiator_coppers > 0:
                transfer(
                    amount=locked_session.initiator_coppers,
                    reason=f"trade #{locked_session.pk}",
                    from_purse=get_or_create_purse(locked_session.initiator_sheet),
                    to_purse=get_or_create_purse(locked_session.counterparty_sheet),
                )
            if locked_session.counterparty_coppers > 0:
                transfer(
                    amount=locked_session.counterparty_coppers,
                    reason=f"trade #{locked_session.pk}",
                    from_purse=get_or_create_purse(locked_session.counterparty_sheet),
                    to_purse=get_or_create_purse(locked_session.initiator_sheet),
                )

            locked_session.status = TradeSession.Status.COMPLETED
            locked_session.resolved_at = timezone.now()
            locked_session.save(update_fields=["status", "resolved_at"])
            return locked_session
    except _ABORT_RESETS_CONFIRMS:
        # A bare queryset .update() would bypass SharedMemoryModel's identity
        # map — the cached instance callers (confirm()'s test, the action
        # layer) hold would keep stale in-memory confirm flags even though
        # the row changed. Save through the instance instead so the cache
        # and the row agree (#2990).
        session.initiator_confirmed = False
        session.counterparty_confirmed = False
        session.save(update_fields=["initiator_confirmed", "counterparty_confirmed"])
        raise
