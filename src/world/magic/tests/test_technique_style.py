"""Tests for the TechniqueStyle model."""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.factories import TechniqueStyleFactory
from world.magic.models import TechniqueStyle


class TechniqueStyleModelTests(TestCase):
    """Tests for the TechniqueStyle model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.path_steel = PathFactory(name="Path of Steel")
        cls.path_shadow = PathFactory(name="Path of Shadow")
        cls.style = TechniqueStyle.objects.create(
            name="Manifestation",
            description="Powers that create visible magical effects.",
        )
        cls.style.allowed_paths.add(cls.path_steel, cls.path_shadow)

    def test_technique_style_str(self):
        """Test string representation."""
        self.assertEqual(str(self.style), "Manifestation")

    def test_technique_style_natural_key(self):
        """Test natural_key() returns the name."""
        self.assertEqual(self.style.natural_key(), ("Manifestation",))

    def test_technique_style_get_by_natural_key(self):
        """Test get_by_natural_key() lookup."""
        retrieved = TechniqueStyle.objects.get_by_natural_key("Manifestation")
        self.assertEqual(retrieved, self.style)

    def test_technique_style_allowed_paths(self):
        """Test that technique style can have allowed paths."""
        self.assertEqual(self.style.allowed_paths.count(), 2)
        self.assertIn(self.path_steel, self.style.allowed_paths.all())
        self.assertIn(self.path_shadow, self.style.allowed_paths.all())

    def test_technique_style_name_unique(self):
        """Test that name is unique."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            TechniqueStyle.objects.create(name="Manifestation")

    def test_path_has_allowed_styles_reverse_relation(self):
        """Test that Path has reverse relation to allowed styles."""
        self.assertIn(self.style, self.path_steel.allowed_styles.all())


class TechniqueStyleFactoryTests(TestCase):
    """Tests for the TechniqueStyleFactory."""

    def test_factory_creates_technique_style(self):
        """Test that factory creates a valid TechniqueStyle."""
        style = TechniqueStyleFactory()
        self.assertIsInstance(style, TechniqueStyle)
        self.assertTrue(style.name)

    def test_factory_with_allowed_paths(self):
        """Test factory can add allowed paths via post_generation."""
        path1 = PathFactory(name="Test Path 1")
        path2 = PathFactory(name="Test Path 2")
        style = TechniqueStyleFactory(allowed_paths=[path1, path2])
        self.assertEqual(style.allowed_paths.count(), 2)
        self.assertIn(path1, style.allowed_paths.all())
        self.assertIn(path2, style.allowed_paths.all())

    def test_factory_get_or_create_on_name(self):
        """Test factory uses get_or_create on name."""
        style1 = TechniqueStyleFactory(name="Subtle")
        style2 = TechniqueStyleFactory(name="Subtle")
        self.assertEqual(style1.pk, style2.pk)
