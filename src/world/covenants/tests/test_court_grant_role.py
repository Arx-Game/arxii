"""Tests for auto-provisioning a Court's grant-petition NPCRole (#1718)."""

from unittest import mock

from django.db import IntegrityError
from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.court_grant import ensure_court_grant_role
from world.covenants.factories import CovenantFactory
from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCRole


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

    def test_recovers_cleanly_after_partial_failure_mid_provisioning(self):
        """A failure between NPCRole creation and covenant.save() must not
        leave an orphaned NPCRole behind (#1718 review finding).

        Before the @transaction.atomic fix, each write committed immediately,
        so a crash after NPCRole.objects.create() but before
        covenant.save(update_fields=["court_grant_role"]) left an orphaned
        NPCRole occupying the unique derived name while
        covenant.court_grant_role_id stayed None forever — every subsequent
        call collided on that name with an IntegrityError, with no recovery
        path. Wrapping the whole function in one atomic transaction means a
        mid-provisioning failure rolls back completely, so a retry succeeds
        cleanly instead of permanently failing.
        """
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        expected_name = f"{covenant.name} — Court Master's Grant"

        with (
            mock.patch(
                "world.npc_services.models.CourtGrantOfferDetails.objects.create",
                side_effect=RuntimeError("simulated crash mid-provisioning"),
            ),
            self.assertRaises(RuntimeError),
        ):
            ensure_court_grant_role(covenant)

        # The interrupted attempt must not have left an orphaned NPCRole —
        # that would permanently collide with every future call.
        self.assertFalse(NPCRole.objects.filter(name=expected_name).exists())
        covenant.refresh_from_db()
        self.assertIsNone(covenant.court_grant_role_id)

        # Retrying (as a caller naturally would on the next negotiation
        # attempt) must succeed cleanly — no IntegrityError from a stale
        # name collision.
        try:
            role = ensure_court_grant_role(covenant)
        except IntegrityError:
            self.fail(
                "ensure_court_grant_role raised IntegrityError on retry after a "
                "simulated partial failure — the provisioning is not atomic."
            )
        covenant.refresh_from_db()
        self.assertEqual(covenant.court_grant_role_id, role.pk)
        self.assertEqual(NPCRole.objects.filter(name=expected_name).count(), 1)
