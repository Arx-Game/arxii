"""Verify Covenant<->Organization OneToOne linkage and auto-creation."""

from django.test import TestCase

from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.factories import CovenantFactory
from world.covenants.models import Covenant
from world.societies.factories import OrganizationTypeFactory
from world.societies.models import Organization


class CovenantOrganizationLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Ensure the covenant OrganizationType row exists for Covenant.save() to look up.
        OrganizationTypeFactory(name=COVENANT_ORG_TYPE_NAME)

    def test_covenant_auto_creates_backing_organization(self) -> None:
        covenant = CovenantFactory(name="Test Covenant Alpha")
        self.assertIsNotNone(covenant.organization)
        self.assertEqual(covenant.organization.name, "Test Covenant Alpha")
        self.assertEqual(covenant.organization.org_type.name, COVENANT_ORG_TYPE_NAME)
        self.assertIsNone(covenant.organization.society)

    def test_covenant_organization_is_one_to_one(self) -> None:
        covenant = CovenantFactory(name="Test Covenant Beta")
        self.assertEqual(covenant.organization.covenant, covenant)

    def test_covenant_uses_existing_organization_when_provided(self) -> None:
        covenant_type = OrganizationTypeFactory(name=COVENANT_ORG_TYPE_NAME)
        org = Organization.objects.create(
            name="Pre-built Cov Org",
            society=None,
            org_type=covenant_type,
        )
        covenant = Covenant(
            name="Pre-built Cov Org",
            sworn_objective="test",
            organization=org,
        )
        covenant.save()
        self.assertEqual(covenant.organization_id, org.pk)
        self.assertEqual(Organization.objects.filter(name="Pre-built Cov Org").count(), 1)
