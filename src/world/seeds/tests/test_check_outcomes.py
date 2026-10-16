"""The five canonical check-outcome tiers carry their seeded success levels, whichever
seed creates them first (#4378)."""

from django.test import TestCase

from actions.catalog_seeding import ensure_base_pool
from world.seeds.checks import seed_check_resolution_tables
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.models import CheckOutcome


def _levels() -> dict[str, int]:
    return dict(
        CheckOutcome.objects.filter(name__in=CANONICAL_OUTCOME_LEVELS).values_list(
            "name", "success_level"
        )
    )


class CanonicalOutcomeLevelTests(TestCase):
    def test_pool_seed_that_runs_first_creates_outcomes_at_canonical_levels(self):
        ensure_base_pool(
            name="Probe pool",
            description="",
            consequences=[
                ("Failure", "fail", 1),
                ("Partial Success", "partial", 1),
                ("Success", "win", 1),
            ],
        )
        seed_check_resolution_tables()
        self.assertEqual(_levels(), CANONICAL_OUTCOME_LEVELS)

    def test_seed_corrects_rows_left_at_wrong_levels(self):
        # Production's state: Failure 3, Partial Success -1, Success -4.
        for name, level in (("Failure", 3), ("Partial Success", -1), ("Success", -4)):
            CheckOutcome.objects.create(name=name, success_level=level)
        seed_check_resolution_tables()
        self.assertEqual(_levels(), CANONICAL_OUTCOME_LEVELS)

    def test_seed_leaves_authored_text_alone(self):
        CheckOutcome.objects.create(name="Success", description="Staff wrote this.")
        seed_check_resolution_tables()
        self.assertEqual(CheckOutcome.objects.get(name="Success").description, "Staff wrote this.")
