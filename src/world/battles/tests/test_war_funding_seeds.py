"""Tests for the WAR_FUNDING ContributionMethod seed (#2382).

Mirrors ``test_seed_staging_catalog.py``'s shape: proves the seed creates
three ContributionMethod rows with the correct CheckType references and
placeholder values, plus idempotency (re-running is a no-op).
"""

from __future__ import annotations

from django.test import TestCase

from world.projects.constants import ProjectKind
from world.projects.models import ContributionMethod
from world.seeds.database import seed_dev_database


class SeedWarFundingContributionMethodsTests(TestCase):
    """The WAR_FUNDING ContributionMethod seed row shape and idempotency."""

    def test_seeds_three_methods(self) -> None:
        seed_dev_database()

        methods = ContributionMethod.objects.filter(kind=ProjectKind.WAR_FUNDING).order_by("name")
        self.assertEqual(methods.count(), 3)

        expected = {
            "Drill Troops": "Household Command",
            "Fortify Defenses": "Search",
            "Scout Enemy Positions": "Stealth",
        }
        for method in methods:
            self.assertIn(method.name, expected)
            self.assertEqual(method.check_type.name, expected[method.name])
            self.assertEqual(method.ap_cost, 5)
            self.assertEqual(method.progress_on_success, 10)
            self.assertTrue(method.is_active)

    def test_seed_is_idempotent(self) -> None:
        seed_dev_database()
        seed_dev_database()

        self.assertEqual(
            ContributionMethod.objects.filter(kind=ProjectKind.WAR_FUNDING).count(),
            3,
        )
