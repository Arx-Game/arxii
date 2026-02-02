"""Tests for the ResonanceAssociation model."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import ResonanceAssociationFactory
from world.magic.models import ResonanceAssociation


class ResonanceAssociationModelTests(TestCase):
    """Tests for the ResonanceAssociation model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.association = ResonanceAssociation.objects.create(
            name="Test Spiders",
            description="Webs, cunning, patience, and predation.",
            category="Animals",
        )

    def test_resonance_association_str_with_category(self):
        """Test string representation with category."""
        self.assertEqual(str(self.association), "Test Spiders (Animals)")

    def test_resonance_association_str_without_category(self):
        """Test string representation without category."""
        assoc = ResonanceAssociation.objects.create(name="Darkness")
        self.assertEqual(str(assoc), "Darkness")

    def test_resonance_association_natural_key(self):
        """Test natural_key() returns the name."""
        self.assertEqual(self.association.natural_key(), ("Test Spiders",))

    def test_resonance_association_get_by_natural_key(self):
        """Test get_by_natural_key() lookup."""
        retrieved = ResonanceAssociation.objects.get_by_natural_key("Test Spiders")
        self.assertEqual(retrieved, self.association)

    def test_resonance_association_name_unique(self):
        """Test that name is unique."""
        with self.assertRaises(IntegrityError):
            ResonanceAssociation.objects.create(name="Test Spiders")

    def test_resonance_association_ordering_by_category_then_name(self):
        """Test that associations are ordered by category, then name."""
        # Clear existing and create test data in specific order
        ResonanceAssociation.objects.all().delete()

        # Create in non-alphabetical order
        fire = ResonanceAssociation.objects.create(name="Test Fire", category="Elements")
        wolves = ResonanceAssociation.objects.create(name="Test Wolves", category="Animals")
        water = ResonanceAssociation.objects.create(name="Test Water", category="Elements")
        spiders = ResonanceAssociation.objects.create(name="Test Spiders", category="Animals")
        shadows = ResonanceAssociation.objects.create(name="Test Shadows", category="")

        # Query and verify order
        all_associations = list(ResonanceAssociation.objects.all())

        # Empty category comes first alphabetically, then Animals, then Elements
        expected_order = [shadows, spiders, wolves, fire, water]
        self.assertEqual(all_associations, expected_order)


class ResonanceAssociationFactoryTests(TestCase):
    """Tests for the ResonanceAssociationFactory."""

    def test_factory_creates_resonance_association(self):
        """Test that factory creates a valid ResonanceAssociation."""
        association = ResonanceAssociationFactory()
        self.assertIsInstance(association, ResonanceAssociation)
        self.assertTrue(association.name)

    def test_factory_with_category(self):
        """Test factory with category specified."""
        association = ResonanceAssociationFactory(
            name="Test Fire", category="Elements", description="Heat, transformation, passion"
        )
        self.assertEqual(association.name, "Test Fire")
        self.assertEqual(association.category, "Elements")
        self.assertEqual(association.description, "Heat, transformation, passion")

    def test_factory_get_or_create_on_name(self):
        """Test factory uses get_or_create on name."""
        assoc1 = ResonanceAssociationFactory(name="Wolves")
        assoc2 = ResonanceAssociationFactory(name="Wolves")
        self.assertEqual(assoc1.pk, assoc2.pk)
