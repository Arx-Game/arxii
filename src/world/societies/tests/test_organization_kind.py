"""Tests for the Organization.kind discriminator and related rank-title behavior."""

from django.test import TestCase

from world.societies.constants import OrganizationKind
from world.societies.models import Organization


class OrganizationKindFieldTests(TestCase):
    def test_organization_has_kind_field(self) -> None:
        """Organization.kind is a TextChoices field on Organization."""
        field_names = {f.name for f in Organization._meta.get_fields()}
        self.assertIn("kind", field_names)

    def test_kind_field_uses_organization_kind_choices(self) -> None:
        kind_field = Organization._meta.get_field("kind")
        choices_values = {value for value, _ in kind_field.choices}
        self.assertEqual(choices_values, set(OrganizationKind.values))


class OrganizationKindRequiredTests(TestCase):
    def test_kind_is_required(self) -> None:
        """Organization.kind cannot be null after Task A5."""
        kind_field = Organization._meta.get_field("kind")
        self.assertFalse(kind_field.null)

    def test_org_type_fk_is_removed(self) -> None:
        """Organization.org_type FK is dropped — kind is the discriminator."""
        field_names = {f.name for f in Organization._meta.get_fields()}
        self.assertNotIn("org_type", field_names)
