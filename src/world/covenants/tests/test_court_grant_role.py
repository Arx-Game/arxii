"""Tests for auto-provisioning a Court's grant-petition NPCRole (#1718)."""

from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.court_grant import ensure_court_grant_role
from world.covenants.factories import CovenantFactory
from world.npc_services.constants import OfferKind


class EnsureCourtGrantRoleTests(TestCase):
    def test_creates_role_and_offer_on_first_call(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        role = ensure_court_grant_role(covenant)
        covenant.refresh_from_db()
        self.assertEqual(covenant.court_grant_role_id, role.pk)
        self.assertEqual(role.faction_affiliation_id, covenant.organization_id)
        offer = role.offers.get(kind=OfferKind.COURT_GRANT)
        self.assertEqual(offer.court_grant_offer_details.covenant_id, covenant.pk)

    def test_idempotent_on_second_call(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        first = ensure_court_grant_role(covenant)
        second = ensure_court_grant_role(covenant)
        self.assertEqual(first.pk, second.pk)
