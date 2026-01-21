"""Tests for distinction models."""

from django.test import TestCase

from world.distinctions.models import DistinctionCategory


class DistinctionCategoryTests(TestCase):
    """Test DistinctionCategory model."""

    def test_category_creation(self):
        """Test basic category creation."""
        category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Body, health, constitution",
            display_order=1,
        )
        self.assertEqual(category.name, "Physical")
        self.assertEqual(category.slug, "physical")
        self.assertEqual(category.display_order, 1)

    def test_category_str(self):
        """Test __str__ returns name."""
        category = DistinctionCategory.objects.create(
            name="Mental",
            slug="mental",
        )
        self.assertEqual(str(category), "Mental")

    def test_category_ordering(self):
        """Test categories order by display_order."""
        cat_b = DistinctionCategory.objects.create(name="B", slug="b", display_order=2)
        cat_a = DistinctionCategory.objects.create(name="A", slug="a", display_order=1)
        categories = list(DistinctionCategory.objects.all())
        self.assertEqual(categories, [cat_a, cat_b])
