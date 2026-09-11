"""The XP ledger: the account's pool, and the per-character attribution beside it (#3748).

XP is earned, held and spent by the **account** (ADR-0053) — that does not change here.
What changes is that every movement now says which character it was *about*, because
"how much has this player invested in this character" is a question the game needs to
answer: the death-kudos cap (ADR-0131) is sized on a character's lifetime XP spend, and
future character-loss reimbursement will read the same number.

Two records are written per movement:

* ``XPTransaction`` — the account's audit trail, now stamped with ``character``.
* ``CharacterXP`` + ``CharacterXPTransaction`` — the character's own running totals.

The character ledger is **attribution, not a second pool**. Nothing is debited from it
when XP is spent; ``total_spent`` is a lifetime counter that may exceed ``total_earned``,
because a player can pour XP earned on one character into another. The one exception is
the non-transferable row CG conversion writes (``award_cg_conversion_xp``), which *is* a
pool locked to its character — see ``CharacterXP``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from evennia.accounts.models import AccountDB

from world.progression.exceptions import InsufficientXPError, NoAccountForCharacterError
from world.progression.models import (
    CharacterXP,
    CharacterXPTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.types import ProgressionReason

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_or_create_xp_tracker(account: AccountDB) -> ExperiencePointsData:
    """Get or create the account's XP pool row."""
    xp_tracker, _created = ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={
            "total_earned": 0,
            "total_spent": 0,
        },
    )
    return xp_tracker


def _attribution_row(sheet: CharacterSheet) -> CharacterXP:
    """The character's transferable attribution row, locked for update.

    ``select_for_update`` before ``get_or_create`` mirrors ``award_development_points``'s
    handling of the same shape (an FK, not a unique constraint): concurrent awards on one
    character serialize instead of racing two rows into existence.
    """
    row, _created = CharacterXP.objects.select_for_update().get_or_create(
        character=sheet,
        transferable=True,
        defaults={"total_earned": 0, "total_spent": 0},
    )
    return row


def record_character_earn(
    sheet: CharacterSheet | None,
    amount: int,
    reason: str,
    description: str,
) -> None:
    """Credit ``amount`` to the character's lifetime earned, with a ledger row.

    A ``None`` sheet is a no-op: some awards genuinely have no character behind them
    (a GM story reward pays the GM's account for running a scene, not a character).
    Call inside the caller's atomic block — the account pool and the attribution must
    move together or not at all.
    """
    if sheet is None:
        return
    row = _attribution_row(sheet)
    row.award_xp(amount)
    CharacterXPTransaction.objects.create(
        character=sheet,
        amount=amount,
        reason=reason,
        description=description,
        transferable=True,
    )


def record_character_spend(
    sheet: CharacterSheet,
    amount: int,
    reason: str,
    description: str,
) -> None:
    """Add ``amount`` to the character's lifetime spent, with a ledger row.

    Deliberately not ``CharacterXP.spend_xp``: that method guards a pool against
    overdraft, and this counter is not a pool. Spending more on a character than was
    ever earned on them is the normal case for a second character.
    """
    row = _attribution_row(sheet)
    row.total_spent += amount
    row.save(update_fields=["total_spent", "updated_date"])
    CharacterXPTransaction.objects.create(
        character=sheet,
        amount=-amount,
        reason=reason,
        description=description,
        transferable=True,
    )


def spend_xp_for_character(
    sheet: CharacterSheet,
    amount: int,
    description: str,
    *,
    reason: str = ProgressionReason.XP_PURCHASE,
    gm: AccountDB | None = None,
) -> XPTransaction | None:
    """Debit the account's pool for something bought for ``sheet``, and attribute it.

    The single seam every XP purchase goes through — class-level unlocks, skill
    breakthroughs, gift unlocks, thread-weaving unlocks, distinction sheet changes.
    Before #3748 each of those repeated the same four steps by hand, and while all five
    stamped ``XPTransaction.character``, not one of them touched ``CharacterXP`` — so the
    death-kudos cap, which reads that ledger, read a number nobody maintained.

    Returns ``None`` for a free purchase (``amount <= 0``) so callers can keep
    authoring zero-cost unlocks without a phantom transaction.

    Raises:
        NoAccountForCharacterError: The sheet has no linked account.
        InsufficientXPError: The pool cannot cover ``amount``; carries
            ``required``/``available`` so callers can phrase their own refusal.
    """
    if amount <= 0:
        return None

    account = sheet.character.account
    if account is None:
        raise NoAccountForCharacterError

    with transaction.atomic():
        xp_tracker = get_or_create_xp_tracker(account)
        if not xp_tracker.spend_xp(amount):
            raise InsufficientXPError(required=amount, available=xp_tracker.current_available)

        record_character_spend(sheet, amount, reason, description)

        return XPTransaction.objects.create(
            account=account,
            amount=-amount,
            reason=reason,
            description=description,
            character=sheet,
            gm=gm,
        )
