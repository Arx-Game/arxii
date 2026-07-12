"""Office appointment + domain-admin gate tests (#2239)."""

from __future__ import annotations

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.constants import DOMAIN_STEWARD_OFFICE
from world.societies.houses.services import (
    can_administer_domain,
    create_domain,
    is_org_leader,
)
from world.societies.models import OrganizationOffice
from world.societies.office_services import (
    appoint_office,
    holds_office,
    office_holder,
    vacate_office,
)

_STEWARD_TITLE = "Minister of the Domains"


class OfficeServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory(name="House Westrock")
        cls.holder = PersonaFactory()
        cls.other = PersonaFactory()

    def test_appoint_creates_office_and_sets_holder(self):
        office = appoint_office(
            organization=self.org,
            slug=DOMAIN_STEWARD_OFFICE,
            holder=self.holder,
            title=_STEWARD_TITLE,
        )
        self.assertEqual(office.holder, self.holder)
        self.assertEqual(office.title, _STEWARD_TITLE)
        self.assertTrue(holds_office(self.holder, self.org, DOMAIN_STEWARD_OFFICE))
        self.assertEqual(office_holder(self.org, DOMAIN_STEWARD_OFFICE), self.holder)

    def test_reappoint_replaces_holder_without_duplicating_office(self):
        appoint_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE, holder=self.holder)
        appoint_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE, holder=self.other)
        self.assertEqual(
            OrganizationOffice.objects.filter(
                organization=self.org, slug=DOMAIN_STEWARD_OFFICE
            ).count(),
            1,
        )
        self.assertEqual(office_holder(self.org, DOMAIN_STEWARD_OFFICE), self.other)
        self.assertFalse(holds_office(self.holder, self.org, DOMAIN_STEWARD_OFFICE))

    def test_vacate_clears_holder_and_is_a_noop_when_absent(self):
        appoint_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE, holder=self.holder)
        vacate_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE)
        self.assertIsNone(office_holder(self.org, DOMAIN_STEWARD_OFFICE))
        # Vacating an already-vacant / never-created office does not raise.
        vacate_office(organization=self.org, slug="no-such-office")


class DomainAdminGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory(name="House Westrock")
        cls.domain = create_domain(area=AreaFactory(), name="Westrock Vale", owner_org=cls.org)
        cls.leader = PersonaFactory()
        cls.base_member = PersonaFactory()
        cls.steward = PersonaFactory()
        cls.stranger = PersonaFactory()
        OrganizationMembershipFactory(organization=cls.org, persona=cls.leader, rank=1)
        OrganizationMembershipFactory(organization=cls.org, persona=cls.base_member)

    def test_is_org_leader_only_for_manage_ranks_rung(self):
        self.assertTrue(is_org_leader(self.leader, self.org))
        self.assertFalse(is_org_leader(self.base_member, self.org))
        self.assertFalse(is_org_leader(self.stranger, self.org))

    def test_leader_may_administer_domain(self):
        self.assertTrue(can_administer_domain(self.leader, self.domain))

    def test_steward_office_holder_may_administer_domain(self):
        self.assertFalse(can_administer_domain(self.steward, self.domain))
        appoint_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE, holder=self.steward)
        self.assertTrue(can_administer_domain(self.steward, self.domain))

    def test_base_member_and_stranger_may_not_administer_domain(self):
        self.assertFalse(can_administer_domain(self.base_member, self.domain))
        self.assertFalse(can_administer_domain(self.stranger, self.domain))
