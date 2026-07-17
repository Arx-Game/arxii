"""OrganizationObligation + settlement via Golden Hares (#2428).

Per-test setUp (not setUpTestData): these tests walk ``sheet.character``,
and Evennia typeclass instances are not deepcopy-safe as class-level test
data (see world.currency.tests.test_favor_tokens for the same convention).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import mint_favor_token
from world.societies.constants import ObligationOrigin, ObligationState
from world.societies.exceptions import ObligationNotOwedError
from world.societies.factories import OrganizationFactory, OrganizationObligationFactory
from world.societies.models import OrganizationObligation
from world.societies.obligation_services import has_open_obligation, settle_obligation


class SettleObligationTests(TestCase):
    def setUp(self):
        self.academy = OrganizationFactory()
        self.debtor = CharacterSheetFactory()
        self.obligation = OrganizationObligationFactory(
            debtor=self.debtor,
            creditor=self.academy,
            origin=ObligationOrigin.ACADEMY_ENTRANCE,
            state=ObligationState.OWED,
        )
        self.token = mint_favor_token(
            self.academy,
            self.debtor,
            provenance_note="Entrance fee, paid in kind",
        )

    def test_settle_happy_path_redeems_token_and_stamps_row(self):
        settle_obligation(self.obligation, self.token)

        row = OrganizationObligation.objects.get(pk=self.obligation.pk)
        self.assertEqual(row.state, ObligationState.SETTLED)
        self.assertIsNotNone(row.settled_at)
        self.assertEqual(row.settled_by_token_id, self.token.pk)

        token_row = self.token.__class__.objects.get(pk=self.token.pk)
        self.assertIsNotNone(token_row.redeemed_at)

    def test_settle_updates_the_passed_in_instance_too(self):
        settle_obligation(self.obligation, self.token)

        self.assertEqual(self.obligation.state, ObligationState.SETTLED)
        self.assertIsNotNone(self.obligation.settled_at)
        self.assertEqual(self.obligation.settled_by_token_id, self.token.pk)

    def test_settle_non_owed_raises(self):
        settle_obligation(self.obligation, self.token)
        second_token = mint_favor_token(self.academy, self.debtor, provenance_note="A second deed")
        with self.assertRaises(ObligationNotOwedError):
            settle_obligation(self.obligation, second_token)

    def test_settle_with_token_from_a_different_org_raises_and_leaves_state_owed(self):
        other_org = OrganizationFactory()
        foreign_token = mint_favor_token(
            other_org, self.debtor, provenance_note="A rival org's deed"
        )
        with self.assertRaises(ValidationError):
            settle_obligation(self.obligation, foreign_token)

        row = OrganizationObligation.objects.get(pk=self.obligation.pk)
        self.assertEqual(row.state, ObligationState.OWED)
        self.assertIsNone(row.settled_at)

    def test_settled_row_survives_as_history(self):
        settle_obligation(self.obligation, self.token)
        self.assertTrue(OrganizationObligation.objects.filter(pk=self.obligation.pk).exists())


class HasOpenObligationTests(TestCase):
    def setUp(self):
        self.academy = OrganizationFactory()
        self.debtor = CharacterSheetFactory()

    def test_true_when_an_owed_row_exists(self):
        OrganizationObligationFactory(
            debtor=self.debtor, creditor=self.academy, state=ObligationState.OWED
        )
        self.assertTrue(has_open_obligation(self.debtor, self.academy))

    def test_false_when_no_row_exists(self):
        self.assertFalse(has_open_obligation(self.debtor, self.academy))

    def test_false_once_settled(self):
        obligation = OrganizationObligationFactory(
            debtor=self.debtor, creditor=self.academy, state=ObligationState.OWED
        )
        token = mint_favor_token(self.academy, self.debtor, provenance_note="Paid up")
        settle_obligation(obligation, token)
        self.assertFalse(has_open_obligation(self.debtor, self.academy))

    def test_false_for_settled_by_sponsor_row(self):
        OrganizationObligationFactory(
            debtor=self.debtor,
            creditor=self.academy,
            state=ObligationState.SETTLED_BY_SPONSOR,
        )
        self.assertFalse(has_open_obligation(self.debtor, self.academy))

    def test_scoped_to_the_specific_org(self):
        other_org = OrganizationFactory()
        OrganizationObligationFactory(
            debtor=self.debtor, creditor=self.academy, state=ObligationState.OWED
        )
        self.assertFalse(has_open_obligation(self.debtor, other_org))
