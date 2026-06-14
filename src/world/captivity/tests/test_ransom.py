"""Ransom demand & payment tests (#931)."""

from django.test import TestCase

from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import (
    InsufficientTreasuryError,
    NoCaptorError,
    NoRansomError,
    NotHeldError,
)
from world.captivity.ransom import _RANSOM_FLOOR_COPPERS, demand_ransom, pay_ransom
from world.captivity.services import capture_character
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.currency.constants import ContractStatus
from world.currency.services import get_or_create_treasury, transfer
from world.societies.factories import OrganizationFactory


class DemandRansomTests(TestCase):
    def test_demand_creates_a_floored_contract_linked_to_the_captivity(self) -> None:
        captor = OrganizationFactory()
        family = OrganizationFactory()
        captivity = capture_character(captive=CharacterSheetFactory(), captor_organization=captor)

        contract = demand_ransom(captivity, paying_organization=family)

        assert contract.proposer_organization == captor
        assert contract.counterparty_organization == family
        assert contract.status == ContractStatus.PROPOSED
        term = contract.payment_terms.get()
        assert term.amount == _RANSOM_FLOOR_COPPERS  # no income figure yet → floor
        assert term.recurring is False
        captivity.refresh_from_db()
        assert captivity.ransom_contract == contract

    def test_gm_amount_overrides_the_default(self) -> None:
        captivity = capture_character(
            captive=CharacterSheetFactory(), captor_organization=OrganizationFactory()
        )
        contract = demand_ransom(captivity, paying_organization=OrganizationFactory(), amount=5_000)
        assert contract.payment_terms.get().amount == 5_000

    def test_demand_without_a_captor_is_rejected(self) -> None:
        captivity = capture_character(captive=CharacterSheetFactory())  # no captor org

        with self.assertRaises(NoCaptorError):
            demand_ransom(captivity, paying_organization=OrganizationFactory())


class PayRansomTests(TestCase):
    def _held_with_demand(self, *, fund: int):
        captor = OrganizationFactory()
        family = OrganizationFactory()
        captivity = capture_character(captive=CharacterSheetFactory(), captor_organization=captor)
        demand_ransom(captivity, paying_organization=family)
        if fund:
            transfer(amount=fund, reason="seed", to_treasury=get_or_create_treasury(family))
        return captivity, captor, family

    def test_paying_frees_the_captive_and_moves_the_money(self) -> None:
        captivity, captor, family = self._held_with_demand(fund=_RANSOM_FLOOR_COPPERS + 500)

        pay_ransom(captivity)

        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED
        captivity.captive.refresh_from_db()
        assert captivity.captive.lifecycle_state == LifecycleState.ALIVE
        assert get_or_create_treasury(captor).balance == _RANSOM_FLOOR_COPPERS
        assert get_or_create_treasury(family).balance == 500
        captivity.ransom_contract.refresh_from_db()
        assert captivity.ransom_contract.status == ContractStatus.COMPLETED

    def test_insufficient_treasury_is_rejected(self) -> None:
        captivity, _captor, _family = self._held_with_demand(fund=0)

        with self.assertRaises(InsufficientTreasuryError):
            pay_ransom(captivity)
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.HELD  # still held — no partial state

    def test_paying_a_captivity_without_a_demand_is_rejected(self) -> None:
        captivity = capture_character(
            captive=CharacterSheetFactory(), captor_organization=OrganizationFactory()
        )

        with self.assertRaises(NoRansomError):
            pay_ransom(captivity)

    def test_paying_an_already_resolved_captivity_is_rejected(self) -> None:
        captivity, _captor, _family = self._held_with_demand(fund=_RANSOM_FLOOR_COPPERS)
        pay_ransom(captivity)

        with self.assertRaises(NotHeldError):
            pay_ransom(captivity)
