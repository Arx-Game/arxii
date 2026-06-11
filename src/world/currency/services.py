"""Currency services (#925): the one path money moves through.

``transfer`` is the single mutation point — every faucet, sink, payment,
tithe, and fee in the economy routes here (mission rewards replace their
money stub with a mint-shaped call; permits/teaching fees route their costs
as sinks or transfers). Atomic, row-locked, audited.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.currency.constants import DENOMINATION_VALUES, MINT_FEE_PCT, format_coppers
from world.currency.models import (
    CharacterPurse,
    CurrencyInstrumentDetails,
    CurrencyTransfer,
    OrganizationTreasury,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.societies.models import Organization


def get_or_create_purse(character_sheet: CharacterSheet) -> CharacterPurse:
    purse, _ = CharacterPurse.objects.get_or_create(character_sheet=character_sheet)
    return purse


def get_or_create_treasury(organization: Organization) -> OrganizationTreasury:
    treasury, _ = OrganizationTreasury.objects.get_or_create(organization=organization)
    return treasury


def can_spend_treasury(treasury: OrganizationTreasury, persona: Persona) -> bool:
    """Spend authority: an active membership at rank <= spend_rank_max."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        persona=persona,
        organization_id=treasury.organization_id,
        rank__lte=treasury.spend_rank_max,
    ).exists()


def transfer(  # noqa: PLR0913 - source/destination pairs are co-equal by design
    *,
    amount: int,
    reason: str,
    from_purse: CharacterPurse | None = None,
    from_treasury: OrganizationTreasury | None = None,
    to_purse: CharacterPurse | None = None,
    to_treasury: OrganizationTreasury | None = None,
) -> CurrencyTransfer:
    """Move ``amount`` coppers; null source = mint (faucet), null dest = sink.

    Atomic with row locks; raises ValidationError on a non-positive amount,
    a void transfer (no source AND no destination), double sources or
    destinations, or insufficient funds.
    """
    if amount <= 0:
        msg = "Transfers move a positive number of coppers."
        raise ValidationError(msg)
    if from_purse is not None and from_treasury is not None:
        msg = "A transfer has at most one source."
        raise ValidationError(msg)
    if to_purse is not None and to_treasury is not None:
        msg = "A transfer has at most one destination."
        raise ValidationError(msg)
    source = from_purse or from_treasury
    destination = to_purse or to_treasury
    if source is None and destination is None:
        msg = "A transfer needs a source or a destination."
        raise ValidationError(msg)

    with transaction.atomic():
        if source is not None:
            source = type(source).objects.select_for_update().get(pk=source.pk)
            if source.balance < amount:
                msg = f"Insufficient funds: {format_coppers(source.balance)} on hand."
                raise ValidationError(msg)
            source.balance -= amount
            source.save(update_fields=["balance"])
        if destination is not None:
            destination = type(destination).objects.select_for_update().get(pk=destination.pk)
            destination.balance += amount
            destination.save(update_fields=["balance"])
        return CurrencyTransfer.objects.create(
            from_purse=from_purse,
            from_treasury=from_treasury,
            to_purse=to_purse,
            to_treasury=to_treasury,
            amount=amount,
            reason=reason,
        )


def _instrument_template(denomination: str):
    """Lazy ItemTemplate per denomination (repo bans seed migrations).

    PLACEHOLDER descriptions — instrument flavor text is an authored-content
    pass for Apostate.
    """
    from world.currency.constants import Denomination  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415

    label = Denomination(denomination).label
    template, _ = ItemTemplate.objects.get_or_create(
        name=f"{label} (coin)",
        defaults={
            "description": (
                f"PLACEHOLDER A minted {label}, worth "
                f"{format_coppers(DENOMINATION_VALUES[denomination])}."
            ),
        },
    )
    return template


def mint_instrument(
    *,
    denomination: str,
    holder_sheet: CharacterSheet,
    from_purse: CharacterPurse | None = None,
    from_treasury: OrganizationTreasury | None = None,
) -> ItemInstance:
    """Convert ledger money into a physical coin (face value + mint fee).

    The fee is a sink (#923); the face value is *conserved* — it leaves the
    ledger and lives inside the instrument until redemption.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415

    face_value = DENOMINATION_VALUES[denomination]
    fee = int(face_value * MINT_FEE_PCT)
    with transaction.atomic():
        transfer(
            amount=face_value,
            reason=f"mint {denomination}",
            from_purse=from_purse,
            from_treasury=from_treasury,
        )
        if fee:
            transfer(
                amount=fee,
                reason=f"mint fee {denomination}",
                from_purse=from_purse,
                from_treasury=from_treasury,
            )
        instance = ItemInstance.objects.create(
            template=_instrument_template(denomination),
            holder_character_sheet=holder_sheet,
        )
        CurrencyInstrumentDetails.objects.create(
            item_instance=instance,
            denomination=denomination,
            face_value=face_value,
        )
    return instance


def redeem_instrument(
    *,
    instance: ItemInstance,
    to_purse: CharacterPurse | None = None,
    to_treasury: OrganizationTreasury | None = None,
) -> CurrencyTransfer:
    """Convert a physical coin back into ledger money (fee-free).

    Consumes the instrument (the coin is melted back into the books).
    """
    details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
    with transaction.atomic():
        row = transfer(
            amount=details.face_value,
            reason=f"redeem {details.denomination}",
            to_purse=to_purse,
            to_treasury=to_treasury,
        )
        instance.delete()
    return row
