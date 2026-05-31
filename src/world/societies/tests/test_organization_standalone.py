"""Verify Organization.society can be null for standalone organizations."""

from django.test import TestCase

from world.societies.factories import OrganizationTypeFactory
from world.societies.models import Organization


class OrganizationStandaloneTests(TestCase):
    def test_organization_can_have_null_society(self) -> None:
        """Standalone orgs (e.g., covenants) exist independently of any Society."""
        covenant_type = OrganizationTypeFactory(name="covenant")
        org = Organization.objects.create(
            name="Standalone Covenant Test",
            society=None,
            org_type=covenant_type,
        )
        self.assertIsNone(org.society)
        self.assertEqual(org.org_type.name, "covenant")
