"""Family admin (#4213): a family's kin and slot pools sit on its change page, and a
person added through the Kin inline gets the membership the tree builders read.

``Kinsperson.family`` is a denormalized copy of the primary ``FamilyMembership``;
``family_tree_for`` reads memberships, not that column, so an admin add that wrote only
the FK would show on this page and on no tree. The POST test asserts the whole chain.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.roster.constants import DefinitionTier, MembershipBasis
from world.roster.factories import FamilyFactory, KinSlotPoolFactory
from world.roster.models import FamilyMembership, Kinsperson
from world.roster.services import kinship
from world.roster.services.kinship import OMNISCIENT
from world.societies.factories import OrganizationFactory


class FamilyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = AccountFactory(is_staff=True, is_superuser=True)
        cls.family = FamilyFactory(name="Tallow")
        cls.member = kinship.create_person(name="Aldous Tallow", family=cls.family)
        cls.pool = KinSlotPoolFactory(
            family=cls.family, description="children of the ferrymen", count_remaining=2
        )

    def _change_url(self) -> str:
        return reverse("admin:arxii_family_change", args=[self.family.pk])

    def _post_data(self, **overrides: str) -> dict[str, str]:
        """The change form as the page posts it: the family's own fields, the existing
        member's row unchanged, and no pool rows."""
        data = {
            "name": self.family.name,
            "kind": str(self.family.kind_id),
            "influence": "0",
            "description": "",
            "is_playable": "on",
            "created_by": "",
            "origin_realm": "",
            "members-TOTAL_FORMS": "1",
            "members-INITIAL_FORMS": "1",
            "members-MIN_NUM_FORMS": "0",
            "members-MAX_NUM_FORMS": "1000",
            "members-0-id": str(self.member.pk),
            "members-0-name": self.member.name,
            "members-0-definition_tier": DefinitionTier.NAME_ONLY,
            "members-0-sheet": "",
            "members-0-gender": "",
            "members-0-age": "",
            "kin_slot_pools-TOTAL_FORMS": "0",
            "kin_slot_pools-INITIAL_FORMS": "0",
            "kin_slot_pools-MIN_NUM_FORMS": "0",
            "kin_slot_pools-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def test_the_change_page_lists_the_familys_kin_and_pools(self) -> None:
        self.client.force_login(self.superuser)
        response = self.client.get(self._change_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aldous Tallow")
        self.assertContains(response, "children of the ferrymen")
        self.assertContains(response, 'name="members-TOTAL_FORMS"')
        self.assertContains(response, 'name="kin_slot_pools-TOTAL_FORMS"')

    def test_a_person_added_on_the_family_page_gets_a_membership(self) -> None:
        self.client.force_login(self.superuser)
        response = self.client.post(
            self._change_url(),
            self._post_data(
                **{
                    "members-TOTAL_FORMS": "2",
                    "members-1-id": "",
                    "members-1-name": "Ismay Tallow",
                    "members-1-definition_tier": DefinitionTier.NAME_ONLY,
                    "members-1-sheet": "",
                    "members-1-gender": "",
                    "members-1-age": "",
                    "members-1-is_appable": "on",
                }
            ),
        )
        self.assertEqual(response.status_code, 302)

        ismay = Kinsperson.objects.get(name="Ismay Tallow")
        self.assertEqual(ismay.family_id, self.family.pk)
        self.assertTrue(ismay.is_appable)
        self.assertEqual(ismay.created_by_id, self.superuser.pk)
        membership = FamilyMembership.objects.get(kinsperson=ismay, family=self.family)
        self.assertEqual(membership.basis, MembershipBasis.BORN)
        self.assertTrue(membership.is_primary)
        # The membership is what the tree reads; the FK alone would not get her here.
        tree_ids = {node["id"] for node in kinship.family_tree_for(self.family, OMNISCIENT).nodes}
        self.assertIn(ismay.pk, tree_ids)

    def test_the_almanach_field_links_a_housed_family(self) -> None:
        org = OrganizationFactory(name="House Tallow", family=self.family)
        self.client.force_login(self.superuser)
        response = self.client.get(self._change_url())
        self.assertContains(response, f"/staff/almanach/houses/{org.pk}")

    def test_the_almanach_field_names_the_gap_for_a_family_without_an_organization(self) -> None:
        self.client.force_login(self.superuser)
        response = self.client.get(self._change_url())
        self.assertContains(response, "No organization")
        self.assertNotContains(response, "/staff/almanach/houses/")
