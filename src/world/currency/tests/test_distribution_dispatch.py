"""The collection-distribution dispatch (#2540, ruled 2026-07-20): debt first, then allowance.

Sequence under test: collect (band + graft as ever) → ``service_debt_principal`` (a flat
``DEBT_PRINCIPAL_GROSS_PCT`` of GROSS toward principal, oldest debt first) → member
allowance from the post-debt remainder of what landed. Outcome bands forced via the
checks helper, mirroring the gem-collection tests.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.models import CurrencyTransfer, DebtInstrument, OrgIncomeStream
from world.currency.services import (
    accrue_income_stream,
    collect_and_distribute,
    get_or_create_economics,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.traits.factories import CheckOutcomeFactory


def _pilot(persona, *, days_ago: int = 1) -> None:
    account = AccountFactory()
    account.last_login = timezone.now() - timedelta(days=days_ago)
    account.save(update_fields=["last_login"])
    character = persona.character_sheet.character
    character.db_account = account
    character.save(update_fields=["db_account"])


class CollectAndDistributeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory(name="House Debtvein")
        cls.creditor = OrganizationFactory(name="House Blighton")
        cls.collector = CharacterSheetFactory().character
        cls.member = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.member, organization=cls.org, rank=2)
        _pilot(cls.member)
        CheckTypeFactory(name="Tax Collection")
        economics = get_or_create_economics(cls.org)
        economics.graft_pct = 10
        economics.save(update_fields=["graft_pct"])

    def setUp(self) -> None:
        self.stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Domain Tax", kind="domain_tax", gross_amount=1000
        )
        accrue_income_stream(self.stream)  # pool 1000

    def _dispatch(self, success_level: int = 1):
        outcome = CheckOutcomeFactory(name=f"band_{success_level}", success_level=success_level)
        with force_check_outcome(outcome):
            return collect_and_distribute(organization=self.org, character=self.collector)

    def _debt(self, principal: int, **kwargs) -> DebtInstrument:
        return DebtInstrument.objects.create(
            debtor_organization=self.org,
            creditor_organization=self.creditor,
            principal=principal,
            **kwargs,
        )

    def test_debt_first_then_allowance_from_remainder(self) -> None:
        debt = self._debt(500)
        result = self._dispatch()
        # Gross 1000 → landed 900 (10% graft). Debt-first: 13% of GROSS = 130.
        self.assertEqual(result.collection.gathered, 1000)
        self.assertEqual(result.collection.landed, 900)
        self.assertEqual(result.debt_principal_paid, 130)
        debt.refresh_from_db()
        self.assertEqual(debt.principal, 370)
        self.assertEqual(get_or_create_treasury(self.creditor).balance, 130)
        # Allowance: 50% of the post-debt remainder (900 - 130 = 770) → 385.
        self.assertEqual(result.allowance.total_distributed, 385)
        self.assertEqual(get_or_create_purse(self.member.character_sheet).balance, 385)
        # The rest stays in the treasury: 900 - 130 - 385.
        self.assertEqual(get_or_create_treasury(self.org).balance, 385)

    def test_small_debt_retires_and_deactivates(self) -> None:
        debt = self._debt(50)  # smaller than the 130 target
        result = self._dispatch()
        self.assertEqual(result.debt_principal_paid, 50)
        debt.refresh_from_db()
        self.assertEqual(debt.principal, 0)
        self.assertFalse(debt.active)

    def test_oldest_debt_services_first(self) -> None:
        older = self._debt(100)
        newer = self._debt(500)
        self._dispatch()  # target 130: 100 retires the older, 30 hits the newer
        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.principal, 0)
        self.assertEqual(newer.principal, 470)

    def test_diverting_debt_is_skipped(self) -> None:
        debt = self._debt(500, diverting=True)
        result = self._dispatch()
        self.assertEqual(result.debt_principal_paid, 0)
        debt.refresh_from_db()
        self.assertEqual(debt.principal, 500)  # the cheat routes past servicing
        self.assertEqual(result.allowance.total_distributed, 450)  # full landed → allowance

    def test_no_debts_allowance_draws_from_full_landed(self) -> None:
        result = self._dispatch()
        self.assertEqual(result.debt_principal_paid, 0)
        self.assertEqual(result.allowance.total_distributed, 450)  # 50% of 900

    def test_catastrophe_distributes_nothing(self) -> None:
        self._debt(500)
        result = self._dispatch(success_level=-2)
        self.assertTrue(result.collection.catastrophe)
        self.assertEqual(result.debt_principal_paid, 0)
        self.assertEqual(result.allowance.total_distributed, 0)
        self.assertFalse(
            CurrencyTransfer.objects.filter(reason__startswith="debt principal").exists()
        )
