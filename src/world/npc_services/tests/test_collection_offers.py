"""COLLECTION / IMPROVEMENT offer kinds (#930): the domain-running summon loop."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.models import DebtInstrument, OrgIncomeStream
from world.currency.services import (
    accrue_income_stream,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.items.factories import MaterialCategoryFactory
from world.items.materials_models import StreamMaterialPool
from world.npc_services.constants import OfferKind
from world.npc_services.effects import (
    OFFER_EFFECT_HANDLERS,
    run_collection,
    run_improvement,
)
from world.npc_services.factories import NPCRoleFactory, NPCServiceOfferFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.traits.factories import CheckOutcomeFactory


def _pilot(persona, *, days_ago: int = 1) -> None:
    """Give ``persona``'s character an account active within the allowance lookback."""
    account = AccountFactory()
    account.last_login = timezone.now() - timedelta(days=days_ago)
    account.save(update_fields=["last_login"])
    character = persona.character_sheet.character
    character.db_account = account
    character.save(update_fields=["db_account"])


class CollectionOfferTests(TestCase):
    def setUp(self) -> None:
        self.family = OrganizationFactory(name="House Testerly")
        self.persona = PersonaFactory()
        OrganizationMembershipFactory(persona=self.persona, organization=self.family, rank=1)
        self.role = NPCRoleFactory(faction_affiliation=self.family)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.COLLECTION, label="Dispatch a collection", is_final=True
        )
        CheckTypeFactory(name="Tax Collection")
        self.stream = OrgIncomeStream.objects.create(
            organization=self.family, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        accrue_income_stream(self.stream)

    def test_both_kinds_registered(self) -> None:
        self.assertIn(OfferKind.COLLECTION.value, OFFER_EFFECT_HANDLERS)
        self.assertIn(OfferKind.IMPROVEMENT.value, OFFER_EFFECT_HANDLERS)

    def test_clean_collection_banks_and_toasts(self) -> None:
        outcome = CheckOutcomeFactory(name="offer_collect_clean", success_level=1)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        treasury = get_or_create_treasury(self.family)
        treasury.refresh_from_db()
        self.assertGreater(treasury.balance, 0)
        self.assertIn("banked", result.message)
        self.assertFalse(result.payload["catastrophe"])
        self.assertEqual(result.payload["auto_sold"], 0)
        self.assertNotIn("surplus stores", result.message)

    def test_catastrophe_toasts_the_loss(self) -> None:
        outcome = CheckOutcomeFactory(name="offer_collect_cata", success_level=-2)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        self.assertTrue(result.payload["catastrophe"])
        self.assertIn("lost", result.message)
        treasury = get_or_create_treasury(self.family)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 0)

    def test_collection_pays_debt_and_allowance_and_reports_both(self) -> None:
        """#2540: a collection routes through collect_and_distribute, so debt principal
        and the member allowance both land alongside the base collection."""
        creditor = OrganizationFactory(name="House Creditly")
        debt = DebtInstrument.objects.create(
            debtor_organization=self.family, creditor_organization=creditor, principal=500
        )
        _pilot(self.persona)
        outcome = CheckOutcomeFactory(name="offer_collect_debt", success_level=1)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        debt.refresh_from_db()
        self.assertLess(debt.principal, 500)
        self.assertGreater(result.payload["debt_principal_paid"], 0)
        self.assertEqual(result.payload["allowance_member_count"], 1)
        self.assertIn("went to the house's creditors", result.message)
        self.assertIn("allowances went out to 1 members", result.message)
        purse = get_or_create_purse(self.persona.character_sheet)
        purse.refresh_from_db()
        self.assertGreater(purse.balance, 0)

    def test_collection_shares_out_materials_and_reports_it(self) -> None:
        """#2540 slice 2: landed materials auto-split among active members, one PLACEHOLDER
        line, only when materials actually went out."""
        category = MaterialCategoryFactory(name="Semiprecious")
        StreamMaterialPool.objects.create(
            income_stream=self.stream, material_category=category, uncollected_value=1000
        )
        _pilot(self.persona)
        outcome = CheckOutcomeFactory(name="offer_collect_materials", success_level=1)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        self.assertEqual(result.payload["material_allowance_member_count"], 1)
        self.assertIn("raw materials were shared out to 1 members", result.message)

    def test_collection_auto_sells_excess_materials_and_reports_it(self) -> None:
        """#2540 slice 2: with no active piloted member to draw the allowance, a big
        enough landing piles into OrgMaterialStock above threshold and auto-sells into
        the treasury, reported once — only when something actually sold."""
        category = MaterialCategoryFactory(name="Cordwood")
        StreamMaterialPool.objects.create(
            income_stream=self.stream, material_category=category, uncollected_value=10_000
        )
        outcome = CheckOutcomeFactory(name="offer_collect_autosell", success_level=1)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        self.assertGreater(result.payload["auto_sold"], 0)
        self.assertIn("surplus stores were sold off for", result.message)
        treasury = get_or_create_treasury(self.family)
        treasury.refresh_from_db()
        self.assertGreaterEqual(treasury.balance, result.payload["auto_sold"])

    def test_catastrophe_pays_no_debt_or_allowance(self) -> None:
        """A catastrophe lands nothing to distribute, so no distribution lines appear."""
        creditor = OrganizationFactory(name="House Creditly")
        debt = DebtInstrument.objects.create(
            debtor_organization=self.family, creditor_organization=creditor, principal=500
        )
        _pilot(self.persona)
        outcome = CheckOutcomeFactory(name="offer_collect_cata_debt", success_level=-2)
        with force_check_outcome(outcome):
            result = run_collection(self.offer, self.persona)
        debt.refresh_from_db()
        self.assertEqual(debt.principal, 500)
        self.assertEqual(result.payload["debt_principal_paid"], 0)
        self.assertEqual(result.payload["allowance_member_count"], 0)
        self.assertNotIn("creditors", result.message)
        self.assertNotIn("allowances", result.message)

    def test_empty_pool_soft_refuses(self) -> None:
        self.stream.uncollected_pool = 0
        self.stream.save(update_fields=["uncollected_pool"])
        result = run_collection(self.offer, self.persona)
        self.assertIn("nothing", result.message.lower())

    def test_no_authority_soft_refuses(self) -> None:
        outsider = PersonaFactory()
        result = run_collection(self.offer, outsider)
        self.assertIn("spending authority", result.message)

    def test_improvement_success_reports_the_gains(self) -> None:
        CheckTypeFactory(name="Domain Investment")
        improve_offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.IMPROVEMENT, label="Invest in the domain", is_final=True
        )
        outcome = CheckOutcomeFactory(name="offer_improve_win", success_level=1)
        with force_check_outcome(outcome):
            result = run_improvement(improve_offer, self.persona)
        self.assertTrue(result.payload["gross_raised"])
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.gross_amount, 1050)


class OfferAPCostTests(TestCase):
    """The generic ap_cost knob charges before dispatch and refuses when broke (#930)."""

    def setUp(self) -> None:
        self.family = OrganizationFactory(name="House Chargely")
        self.persona = PersonaFactory()
        self.character = self.persona.character_sheet.character
        OrganizationMembershipFactory(persona=self.persona, organization=self.family, rank=1)
        self.role = NPCRoleFactory(faction_affiliation=self.family)
        CheckTypeFactory(name="Tax Collection")
        stream = OrgIncomeStream.objects.create(
            organization=self.family, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        accrue_income_stream(stream)

    def _offer(self, ap_cost: int):
        return NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.COLLECTION,
            label=f"collect-ap-{ap_cost}",
            is_final=True,
            ap_cost=ap_cost,
        )

    def test_ap_cost_is_charged_before_dispatch(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.npc_services.services import resolve_offer, start_interaction

        pool = ActionPointPool.get_or_create_for_character(self.character)
        start = pool.current
        offer = self._offer(ap_cost=2)
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        outcome = CheckOutcomeFactory(name="ap_collect", success_level=1)
        with force_check_outcome(outcome):
            resolve_offer(session, offer)
        pool.refresh_from_db()
        self.assertEqual(pool.current, start - 2)

    def test_insufficient_ap_refuses_and_grants_nothing(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.npc_services.services import (
            InsufficientAPError,
            resolve_offer,
            start_interaction,
        )

        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 1
        pool.save(update_fields=["current"])
        offer = self._offer(ap_cost=5)
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        with self.assertRaises(InsufficientAPError):
            resolve_offer(session, offer)
        treasury = get_or_create_treasury(self.family)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 0)  # nothing dispatched
