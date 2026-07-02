"""LOAN offer kind (#930): fiat loans through the summoned-representative loop."""

from django.test import TestCase

from world.currency.models import DebtInstrument
from world.currency.services import get_or_create_treasury
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect, grant_loan
from world.npc_services.factories import NPCRoleFactory, NPCServiceOfferFactory
from world.npc_services.models import LoanOfferDetails
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class GrantLoanTests(TestCase):
    def setUp(self) -> None:
        self.blighton = OrganizationFactory(name="Blighton Bank")
        self.family = OrganizationFactory(name="House Testerly")
        self.persona = PersonaFactory()
        OrganizationMembershipFactory(persona=self.persona, organization=self.family, rank=1)
        self.role = NPCRoleFactory(faction_affiliation=self.blighton)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.LOAN, label="Modest principal", is_final=True
        )
        LoanOfferDetails.objects.create(offer=self.offer, principal=5000, interest_bps_monthly=75)

    def test_accepting_extends_a_fiat_loan(self) -> None:
        result = grant_loan(self.offer, self.persona)

        instrument = DebtInstrument.objects.get(pk=result.object_pk)
        self.assertEqual(instrument.creditor_organization, self.blighton)
        self.assertEqual(instrument.debtor_organization, self.family)
        self.assertEqual(instrument.principal, 5000)
        self.assertEqual(instrument.interest_bps_monthly, 75)
        self.assertEqual(get_or_create_treasury(self.family).balance, 5000)

    def test_dispatch_reaches_the_loan_handler(self) -> None:
        result = dispatch_offer_effect(self.offer, self.persona)
        self.assertEqual(result.kind, OfferKind.LOAN.value)
        self.assertIsNotNone(result.object_pk)

    def test_no_spend_authority_is_a_soft_refusal(self) -> None:
        outsider = PersonaFactory()
        result = grant_loan(self.offer, outsider)
        self.assertIsNone(result.object_pk)
        self.assertIn("spending authority", result.message)
        self.assertFalse(DebtInstrument.objects.filter(debtor_organization=self.family).exists())

    def test_two_authority_orgs_is_a_soft_refusal(self) -> None:
        second = OrganizationFactory(name="House Otherly")
        OrganizationMembershipFactory(persona=self.persona, organization=second, rank=1)
        result = grant_loan(self.offer, self.persona)
        self.assertIsNone(result.object_pk)
        self.assertIn("more than one house", result.message)

    def test_explicit_creditor_overrides_role_faction(self) -> None:
        other_bank = OrganizationFactory(name="Rival Countinghouse")
        details = self.offer.loan_offer_details
        details.creditor_organization = other_bank
        details.save(update_fields=["creditor_organization"])
        result = grant_loan(self.offer, self.persona)
        instrument = DebtInstrument.objects.get(pk=result.object_pk)
        self.assertEqual(instrument.creditor_organization, other_bank)
