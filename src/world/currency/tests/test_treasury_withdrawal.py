"""Discretionary treasury withdrawal (#2540): a spend-authorized member draws to their purse.

The treasury→member outflow #930 never built — gated by ``can_spend_treasury`` (top rank /
the head by default). The house-distribution discretionary-spend primitive.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    withdraw_from_treasury,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class WithdrawFromTreasuryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.leader = PersonaFactory()
        cls.grunt = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.leader, organization=cls.org, rank=1)
        OrganizationMembershipFactory(persona=cls.grunt, organization=cls.org, rank=5)

    def setUp(self) -> None:
        self.treasury = get_or_create_treasury(self.org)
        self.treasury.balance = 1000
        self.treasury.save(update_fields=["balance"])

    def test_authorized_member_withdraws_to_their_purse(self) -> None:
        transfer = withdraw_from_treasury(organization=self.org, persona=self.leader, amount=300)
        self.assertEqual(transfer.amount, 300)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 700)
        purse = get_or_create_purse(self.leader.character_sheet)
        self.assertEqual(purse.balance, 300)

    def test_unauthorized_member_cannot_withdraw(self) -> None:
        with self.assertRaises(ValidationError):
            withdraw_from_treasury(organization=self.org, persona=self.grunt, amount=100)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)  # untouched

    def test_outsider_cannot_withdraw(self) -> None:
        outsider = PersonaFactory()
        with self.assertRaises(ValidationError):
            withdraw_from_treasury(organization=self.org, persona=outsider, amount=100)

    def test_cannot_overdraw_the_treasury(self) -> None:
        with self.assertRaises(ValidationError):
            withdraw_from_treasury(organization=self.org, persona=self.leader, amount=5000)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)  # rejected before any debit
