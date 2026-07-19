"""Boon fulfillment (#2540): move the asked thing from target to asker on a successful ask.

Called by the (future) ``BoonAction.execute`` on a successful roll — the same shape as
``BlackmailAction`` minting Leverage. Only ``MONEY`` is wired: it routes through the single
currency mutation point (``transfer``), target purse → asker purse. ``HELD_ITEM`` awaits an
item-ownership-transfer seam, ``VAULT_ITEM`` awaits the bank/vault system, and ``DEED`` is
RP-only (no mechanical transfer). Idempotent: a fulfilled Boon is a no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.scenes.action_constants import BoonKind

if TYPE_CHECKING:
    from world.scenes.boon_models import Boon


@transaction.atomic
def fulfill_boon(boon: Boon) -> bool:
    """Fulfill a granted Boon. Returns True if it moved value, False for a no-op/RP-only kind.

    Raises ``ValidationError`` (from ``transfer``) if a MONEY boon's target cannot cover it.
    """
    if boon.fulfilled_at is not None:
        return False

    moved = False
    if boon.kind == BoonKind.MONEY and boon.amount > 0:
        from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

        request = boon.action_request
        asker_sheet = request.initiator_persona.character_sheet
        target_sheet = request.target_persona.character_sheet
        transfer(
            amount=boon.amount,
            reason="boon",
            from_purse=get_or_create_purse(target_sheet),
            to_purse=get_or_create_purse(asker_sheet),
        )
        moved = True
    # HELD_ITEM / VAULT_ITEM / DEED: follow-up slices (see #2540).

    boon.fulfilled_at = timezone.now()
    boon.save(update_fields=["fulfilled_at"])
    return moved
