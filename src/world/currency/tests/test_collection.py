"""Active income collection (#930): pools, dispatch outcome matrix, improvement, stasis.

Outcome bands are forced via the checks test helper — magnitudes here mirror the
PLACEHOLDER constants, not a design promise.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.models import IncomeDeclaration, OrgIncomeStream
from world.currency.services import (
    accrue_income_stream,
    collect_org_income,
    get_or_create_economics,
    get_or_create_treasury,
    improve_org_domain,
    settle_obligations,
)
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckOutcomeFactory


class CollectionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.character = CharacterSheetFactory().character
        CheckTypeFactory(name="Tax Collection")
        CheckTypeFactory(name="Domain Investment")
        economics = get_or_create_economics(cls.org)
        economics.graft_pct = 10
        economics.save(update_fields=["graft_pct"])

    def setUp(self) -> None:
        self.taxes = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=600
        )
        self.kickup = OrgIncomeStream.objects.create(
            organization=self.org, name="Turf kick-up", kind="crime_kickup", gross_amount=400
        )
        accrue_income_stream(self.taxes)
        accrue_income_stream(self.kickup)

    def tearDown(self) -> None:
        OrgIncomeStream.objects.filter(organization=self.org).delete()

    def _treasury_balance(self) -> int:
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        return treasury.balance

    def _collect(self, success_level: int):
        outcome = CheckOutcomeFactory(name=f"collect_{success_level}", success_level=success_level)
        with force_check_outcome(outcome):
            return collect_org_income(organization=self.org, character=self.character)

    def test_clean_collection_lands_net_of_graft(self) -> None:
        result = self._collect(1)
        self.assertEqual(result.gathered, 1000)
        self.assertEqual(result.landed, 900)  # 100% band, 10% graft off the aggregate
        self.assertEqual(result.graft_leak, 100)
        self.assertEqual(self._treasury_balance(), 900)
        self.taxes.refresh_from_db()
        self.assertEqual(self.taxes.uncollected_pool, 0)
        # Declarations land per stream, proportional to each pool's share.
        amounts = sorted(
            IncomeDeclaration.objects.filter(stream__organization=self.org).values_list(
                "actual_amount", flat=True
            )
        )
        self.assertEqual(amounts, [360, 540])
        self.assertEqual(sum(amounts), 900)

    def test_critical_collection_carries_goodwill_bonus(self) -> None:
        result = self._collect(2)
        self.assertEqual(result.landed, 990)  # 110% band, then graft
        self.assertEqual(self._treasury_balance(), 990)

    def test_skim_and_waylaid_bands(self) -> None:
        result = self._collect(0)
        self.assertEqual(result.landed, 765)  # 85% band → 850, graft 85
        self.assertGreater(result.stolen, 0)

    def test_waylaid_band(self) -> None:
        result = self._collect(-1)
        self.assertEqual(result.landed, 315)  # 35% band → 350, graft 35

    def test_catastrophe_loses_everything_and_lands_nothing(self) -> None:
        result = self._collect(-2)
        self.assertTrue(result.catastrophe)
        self.assertEqual(result.landed, 0)
        self.assertEqual(self._treasury_balance(), 0)
        self.taxes.refresh_from_db()
        self.kickup.refresh_from_db()
        self.assertEqual(self.taxes.uncollected_pool, 0)  # the money is simply gone
        self.assertEqual(self.kickup.uncollected_pool, 0)
        self.assertFalse(IncomeDeclaration.objects.filter(stream__organization=self.org).exists())

    def test_empty_pools_refuse(self) -> None:
        self._collect(1)
        with self.assertRaises(ValidationError):
            collect_org_income(organization=self.org, character=self.character)

    def test_idle_org_owes_no_new_obligations(self) -> None:
        """Stasis both directions: pooled-but-uncollected income settles nothing."""
        liege = OrganizationFactory()
        from world.currency.models import OrgObligation

        OrgObligation.objects.create(
            from_organization=self.org, to_organization=liege, name="Crown taxes", percent=20
        )
        # Only accrual has happened (setUp) — no declarations exist to settle.
        self.assertEqual(settle_obligations(self.org), [])


class ImprovementTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.character = CharacterSheetFactory().character
        CheckTypeFactory(name="Domain Investment")
        economics = get_or_create_economics(cls.org)
        economics.graft_pct = 10
        economics.save(update_fields=["graft_pct"])

    def setUp(self) -> None:
        self.stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )

    def tearDown(self) -> None:
        OrgIncomeStream.objects.filter(organization=self.org).delete()
        economics = get_or_create_economics(self.org)
        economics.graft_pct = 10
        economics.save(update_fields=["graft_pct"])

    def _improve(self, success_level: int):
        outcome = CheckOutcomeFactory(name=f"improve_{success_level}", success_level=success_level)
        with force_check_outcome(outcome):
            return improve_org_domain(organization=self.org, character=self.character)

    def test_success_raises_gross_and_cracks_graft(self) -> None:
        result = self._improve(1)
        self.assertTrue(result.gross_raised)
        self.assertTrue(result.graft_cracked)
        self.assertEqual(result.new_graft_pct, 9)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.gross_amount, 1050)

    def test_partial_only_cracks_graft(self) -> None:
        result = self._improve(0)
        self.assertFalse(result.gross_raised)
        self.assertTrue(result.graft_cracked)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.gross_amount, 1000)

    def test_failure_changes_nothing(self) -> None:
        result = self._improve(-1)
        self.assertFalse(result.gross_raised)
        self.assertFalse(result.graft_cracked)
        self.assertEqual(result.new_graft_pct, 10)
