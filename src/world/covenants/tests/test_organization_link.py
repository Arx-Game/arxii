"""Verify Covenant<->Organization OneToOne linkage and auto-creation."""

from django.test import TestCase

from world.covenants.factories import CovenantFactory
from world.covenants.models import Covenant
from world.societies.constants import OrganizationKind
from world.societies.models import Organization


class CovenantOrganizationLinkTests(TestCase):
    def test_covenant_auto_creates_backing_organization(self) -> None:
        covenant = CovenantFactory(name="Test Covenant Alpha")
        self.assertIsNotNone(covenant.organization)
        self.assertEqual(covenant.organization.name, "Test Covenant Alpha")
        self.assertEqual(covenant.organization.kind, OrganizationKind.COVENANT)
        self.assertIsNone(covenant.organization.society)

    def test_covenant_organization_is_one_to_one(self) -> None:
        covenant = CovenantFactory(name="Test Covenant Beta")
        self.assertEqual(covenant.organization.covenant, covenant)

    def test_covenant_uses_existing_organization_when_provided(self) -> None:
        org = Organization.objects.create(
            name="Pre-built Cov Org",
            society=None,
            kind=OrganizationKind.COVENANT,
        )
        covenant = Covenant(
            name="Pre-built Cov Org",
            sworn_objective="test",
            organization=org,
        )
        covenant.save()
        self.assertEqual(covenant.organization_id, org.pk)
        self.assertEqual(Organization.objects.filter(name="Pre-built Cov Org").count(), 1)
