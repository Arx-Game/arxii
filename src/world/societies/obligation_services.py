"""Settlement of :class:`~world.societies.models.OrganizationObligation` rows (#2428).

A debtor surrenders a Golden Hare to clear an entrance obligation.
``settle_obligation`` is the only mutation point: it delegates the actual
token surrender to ``world.currency.services.redeem_favor_token`` (Task 1),
which enforces that only the issuing organization can redeem its own Hare,
then flips this row from OWED to SETTLED and stamps provenance. Settled rows
are never deleted (story-significant history, per CLAUDE.md).

Import direction (ADR-0010): societies is the dependent/specific side of the
societies↔currency relationship here (an obligation is a societies concept
that happens to be settled with a currency instrument), so the FK on
``OrganizationObligation`` uses the string ref ``"currency.FavorTokenDetails"``
and this module deferred-imports ``world.currency`` at call time rather than
importing it at module load, matching the rest of this file's cross-app
service calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.societies.constants import ObligationState
from world.societies.exceptions import ObligationNotOwedError
from world.societies.models import OrganizationObligation

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.currency.models import FavorTokenDetails
    from world.societies.models import Organization


@transaction.atomic
def settle_obligation(obligation: OrganizationObligation, token: FavorTokenDetails) -> None:
    """Surrender ``token`` to clear ``obligation`` (#2428).

    Redeems the Hare via ``redeem_favor_token(token, redeemer_org=obligation.creditor)``
    — this is where an issuer mismatch or an already-redeemed token raises
    (``ValidationError``, Task 1's typed surface for those cases). Only after
    a successful redemption does this flip ``obligation.state`` from OWED to
    SETTLED and stamp ``settled_at``/``settled_by_token``.

    Raises:
        ObligationNotOwedError: ``obligation`` is not in the OWED state.
        ValidationError: ``token`` is already redeemed or not issued by
            ``obligation.creditor`` (raised by ``redeem_favor_token``).
    """
    from world.currency.services import redeem_favor_token  # noqa: PLC0415

    locked = OrganizationObligation.objects.select_for_update().get(pk=obligation.pk)
    if locked.state != ObligationState.OWED:
        raise ObligationNotOwedError

    redeem_favor_token(token, redeemer_org=locked.creditor)

    locked.state = ObligationState.SETTLED
    locked.settled_at = timezone.now()
    locked.settled_by_token = token
    locked.save(update_fields=["state", "settled_at", "settled_by_token"])
    obligation.state = locked.state
    obligation.settled_at = locked.settled_at
    obligation.settled_by_token = locked.settled_by_token


def has_open_obligation(sheet: CharacterSheet, org: Organization) -> bool:
    """Whether ``sheet`` currently owes ``org`` an unsettled Golden Hare (#2428).

    Used by Task 6's training gate: an OWED Academy-entrance obligation
    blocks trainers from taking a Prospect on until it's cleared.
    """
    return OrganizationObligation.objects.filter(
        debtor=sheet, creditor=org, state=ObligationState.OWED
    ).exists()
