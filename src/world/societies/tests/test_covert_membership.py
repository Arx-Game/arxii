"""Covert-org membership secrets (#2820 phase 2)."""

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.secrets.constants import SecretProvenance
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationTypeFactory,
)
from world.societies.membership_services import join_organization, promote_member
from world.societies.models import OrganizationRank


class CovertMembershipSecretTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.covert_type = OrganizationTypeFactory(name="spy_network", is_covert=True)
        cls.org = OrganizationFactory(org_type=cls.covert_type)
        cls.persona = PersonaFactory()

    def test_covert_join_mints_subject_secret(self):
        membership = join_organization(self.org, self.persona)
        secret = membership.covert_secret
        self.assertIsNotNone(secret)
        self.assertEqual(secret.subject_sheet_id, self.persona.character_sheet_id)
        self.assertEqual(secret.provenance, SecretProvenance.GM_AUTHORED)
        self.assertTrue(secret.subject_aware)
        # Base rank is tier 5 — a low-level member is level-1 uncommon knowledge.
        self.assertEqual(secret.level, 1)
        self.assertIn("PLACEHOLDER", secret.content)

    def test_promotion_raises_secret_level(self):
        membership = join_organization(self.org, self.persona)
        leader_rank = OrganizationRank.objects.filter(
            organization=self.org, can_manage_ranks=True
        ).first()
        leader = OrganizationMembershipFactory(
            organization=self.org,
            persona=PersonaFactory(),
            rank=leader_rank,
        )
        # Promote 5 -> 4 -> 3 -> 2: tier 2 maps to level 3.
        for _ in range(3):
            membership = promote_member(membership, leader)
        membership.covert_secret.refresh_from_db()
        self.assertEqual(membership.covert_secret.level, 3)

    def test_overt_join_mints_nothing(self):
        overt_org = OrganizationFactory()
        membership = join_organization(overt_org, PersonaFactory())
        self.assertIsNone(membership.covert_secret)

    def test_join_is_idempotent_on_secret(self):
        membership = join_organization(self.org, self.persona)
        first_secret_id = membership.covert_secret_id
        from world.societies.membership_services import sync_covert_membership_secret

        sync_covert_membership_secret(membership)
        membership.refresh_from_db()
        self.assertEqual(membership.covert_secret_id, first_secret_id)
