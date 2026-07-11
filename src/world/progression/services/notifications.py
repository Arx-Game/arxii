"""Live pushes for progression events (#2161).

Central seam: called from ``award_kudos`` post-commit so EVERY kudos award
(pose chip, writeup commend, weekly engagement, spread-assist) surfaces
in-context. msg() to an offline account is a harmless no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

logger = logging.getLogger(__name__)


def notify_kudos_received(
    account: AccountDB, *, amount: int, source_category: str, description: str
) -> None:
    """Push a kudos_received frame to the recipient's connected sessions."""
    payload = {
        "amount": amount,
        "source_category": source_category,
        "description": description,
    }
    try:
        account.msg(kudos_received=((), payload))
    except Exception:
        logger.exception("kudos_received push failed for account %s", account.pk)
