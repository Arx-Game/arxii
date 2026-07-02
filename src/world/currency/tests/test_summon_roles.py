"""Summon-role annotations in the books payload (#930)."""

from django.test import TestCase

from world.currency.services import extend_loan
from world.currency.views import _books_payload
from world.npc_services.factories import NPCRoleFactory
from world.societies.factories import OrganizationFactory


class SummonRoleAnnotationTests(TestCase):
    def setUp(self) -> None:
        self.family = OrganizationFactory(name="House Ledgerly")
        self.blighton = OrganizationFactory(name="Blighton Bank")
        extend_loan(creditor=self.blighton, debtor=self.family, principal=1000, fiat=True)

    def test_debt_rows_carry_the_creditor_representative(self) -> None:
        role = NPCRoleFactory(faction_affiliation=self.blighton)
        payload = _books_payload(self.family)
        self.assertEqual(payload["debts"][0]["summon_role_id"], role.pk)

    def test_steward_role_resolves_from_own_org(self) -> None:
        steward = NPCRoleFactory(faction_affiliation=self.family)
        payload = _books_payload(self.family)
        self.assertEqual(payload["steward_role_id"], steward.pk)

    def test_no_affiliated_role_is_null_not_error(self) -> None:
        payload = _books_payload(self.family)
        self.assertIsNone(payload["steward_role_id"])
        self.assertIsNone(payload["debts"][0]["summon_role_id"])

    def test_disabled_roles_are_not_summonable(self) -> None:
        NPCRoleFactory(faction_affiliation=self.blighton, is_active=False)
        payload = _books_payload(self.family)
        self.assertIsNone(payload["debts"][0]["summon_role_id"])
