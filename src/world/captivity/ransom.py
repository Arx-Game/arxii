"""Ransom demands & payment (#931).

An NPC captor demands payment for a held captive: a one-shot Contract owed by
the captive's family org to the captor org, surfaced on the family books and
settled by ``pay_ransom`` (treasury transfer → frees the captive) — the
pay-from-treasury-vs-rescue fork. The amount is ~1 year of the captive's
income, but until professions/income ledgers exist that figure isn't
computable, so it falls to a flat floor (a GM may always override).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import (
    InsufficientTreasuryError,
    NoCaptorError,
    NoRansomError,
    NotHeldError,
)
from world.captivity.services import resolve_captivity
from world.currency.constants import ContractFormality, ContractStatus
from world.currency.models import Contract, ContractTerm
from world.currency.services import get_or_create_treasury, transfer

if TYPE_CHECKING:
    from world.captivity.models import Captivity
    from world.character_sheets.models import CharacterSheet
    from world.societies.models import Organization

# 1000g floor (1g = 100c), used until incomes are computable. GM may override.
_RANSOM_FLOOR_COPPERS = 100_000


def _estimate_annual_income(captive: CharacterSheet) -> int | None:  # noqa: ARG001
    """A captive's annual income in coppers, for sizing a ~1-year ransom.

    PLACEHOLDER seam (#931): returns None until the income ledger
    (professions/businesses) exists — read it here when it does, and the
    family-org income as a secondary fallback.
    """
    return None


def default_ransom_amount(captive: CharacterSheet) -> int:
    """The captor's default demand: ~1 year of income, else the flat floor."""
    income = _estimate_annual_income(captive)
    return income if income is not None else _RANSOM_FLOOR_COPPERS


def demand_ransom(
    captivity: Captivity,
    *,
    paying_organization: Organization,
    amount: int | None = None,
) -> Contract:
    """Raise the captor's ransom demand against ``paying_organization`` (#931).

    A one-shot HANDSHAKE contract left PROPOSED — the weekly settlement cron
    only touches NOTARIZED+ACTIVE contracts, so this is never auto-paid; it
    waits on the payer's decision (``pay_ransom``) versus a rescue. Links the
    contract onto the captivity. Raises ``NoCaptorError`` without a captor org.
    """
    captor = captivity.captor_organization
    if captor is None:
        raise NoCaptorError
    value = amount if amount is not None else default_ransom_amount(captivity.captive)

    with transaction.atomic():
        contract = Contract.objects.create(
            proposer_organization=captor,
            counterparty_organization=paying_organization,
            # PLACEHOLDER player-facing prose — rewrite in the project voice.
            title=f"PLACEHOLDER: Ransom for {captivity.captive.character.key}",
            terms="PLACEHOLDER. Pay the sum demanded for the captive's safe return.",
            formality=ContractFormality.HANDSHAKE,
            status=ContractStatus.PROPOSED,
        )
        ContractTerm.objects.create(
            contract=contract,
            payer_is_proposer=False,  # the counterparty (family org) pays the captor
            amount=value,
            recurring=False,
        )
        captivity.ransom_contract = contract
        captivity.save(update_fields=["ransom_contract"])
    return contract


def pay_ransom(captivity: Captivity) -> None:
    """Pay a held captive's ransom from the payer org's treasury → frees them.

    Transfers the demanded sum payer→captor, completes the contract, and
    resolves the captivity as RANSOMED. Raises ``NoRansomError`` (no demand),
    ``NotHeldError`` (already resolved), or ``InsufficientTreasuryError``.
    """
    contract = captivity.ransom_contract
    if contract is None:
        raise NoRansomError
    if captivity.status != CaptivityStatus.HELD:
        raise NotHeldError

    term = contract.payment_terms.first()
    if term is None:
        raise NoRansomError
    payer = contract.counterparty_organization
    captor = contract.proposer_organization
    if payer is None or captor is None:
        raise NoRansomError

    payer_treasury = get_or_create_treasury(payer)
    if payer_treasury.balance < term.amount:
        raise InsufficientTreasuryError

    with transaction.atomic():
        transfer(
            amount=term.amount,
            reason="ransom",
            from_treasury=payer_treasury,
            to_treasury=get_or_create_treasury(captor),
        )
        term.fulfilled = True
        term.save(update_fields=["fulfilled"])
        contract.status = ContractStatus.COMPLETED
        contract.signed_at = contract.signed_at or timezone.now()
        contract.save(update_fields=["status", "signed_at"])

    # Freed once paid — outside the txn (it relocates the body / tears the cell).
    resolve_captivity(captivity, status=CaptivityStatus.RANSOMED)
