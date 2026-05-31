"""Verify Organization.society can be null for standalone organizations."""

from django.test import TestCase

from world.societies.constants import OrganizationKind
from world.societies.models import Organization


class OrganizationStandaloneTests(TestCase):
    def test_organization_can_have_null_society(self) -> None:
        """Standalone orgs (e.g., covenants) exist independently of any Society."""
        org = Organization.objects.create(
            name="Standalone Covenant Test",
            society=None,
            kind=OrganizationKind.COVENANT,
        )
        self.assertIsNone(org.society)
        self.assertEqual(org.kind, OrganizationKind.COVENANT)
