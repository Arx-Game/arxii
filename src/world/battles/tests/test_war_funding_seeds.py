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
from world.seeds.tests.content_stub import stub_content_root
from world.seeds.tests.press_helpers import seed_dev_database_with_sample_topup


class SeedWarFundingContributionMethodsTests(TestCase):
    """The WAR_FUNDING ContributionMethod seed row shape and idempotency.

    Backing check-content seeds gate on #2698 (SEED_SAMPLE_CONTENT). Since
    #3017's hard gate, seed_dev_database() itself refuses sampling once the
    stub content root has loaded anything, so the first press runs via
    seed_dev_database_with_sample_topup() (press_helpers.py) - a normal press
    followed by a sampling-on top-up of every cluster seeder. Re-presses after
    that (idempotency checks) use plain seed_dev_database(): sampling is off
    by default, but everything needed already exists from the top-up.
    """

    @stub_content_root()
    def test_seeds_three_methods(self) -> None:
        seed_dev_database_with_sample_topup()

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

    @stub_content_root()
    def test_seed_is_idempotent(self) -> None:
        seed_dev_database_with_sample_topup()
        seed_dev_database()

        self.assertEqual(
            ContributionMethod.objects.filter(kind=ProjectKind.WAR_FUNDING).count(),
            3,
        )
