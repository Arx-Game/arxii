"""Tests for create_resistance_check_types factory helper."""

from django.test import TestCase

from world.checks.factories import create_resistance_check_types
from world.checks.models import CheckTypeTrait


class CreateResistanceCheckTypesTest(TestCase):
    def test_returns_composure_check_type(self):
        result = create_resistance_check_types()

        self.assertIn("Composure", result)

    def test_composure_has_at_least_one_trait(self):
        result = create_resistance_check_types()
        composure = result["Composure"]

        trait_count = CheckTypeTrait.objects.filter(check_type=composure).count()
        self.assertGreaterEqual(
            trait_count,
            1,
            "Composure CheckType has no associated CheckTypeTrait rows",
        )

    def test_composure_uses_social_category(self):
        result = create_resistance_check_types()
        composure = result["Composure"]

        self.assertEqual(composure.category.name, "Social")

    def test_idempotent(self):
        first = create_resistance_check_types()
        second = create_resistance_check_types()

        self.assertEqual(
            first["Composure"].pk,
            second["Composure"].pk,
            "Composure CheckType got a different pk on second call",
        )
        trait_count_after = CheckTypeTrait.objects.filter(check_type=first["Composure"]).count()
        self.assertEqual(
            trait_count_after,
            1,
            "Second call created duplicate CheckTypeTrait rows",
        )
