"""Tests for AggregateBeatContribution ledger model (Task 4.1)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatPredicateType, EraStatus
from world.stories.factories import (
    AggregateBeatContributionFactory,
    BeatFactory,
    EraFactory,
)
from world.stories.models import AggregateBeatContribution


class AggregateBeatContributionModelTests(TestCase):
    def test_contribution_records_points_and_character(self) -> None:
        """Factory creates a row with correct beat, character_sheet, and points."""
        sheet = CharacterSheetFactory()
        beat = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )
        contrib = AggregateBeatContributionFactory(
            beat=beat,
            character_sheet=sheet,
            points=25,
        )

        self.assertEqual(contrib.beat, beat)
        self.assertEqual(contrib.character_sheet, sheet)
        self.assertEqual(contrib.points, 25)
        self.assertIsNone(contrib.roster_entry)
        self.assertIsNone(contrib.era)

    def test_contribution_captures_era(self) -> None:
        """Era FK is stored correctly when provided."""
        era = EraFactory(status=EraStatus.ACTIVE)
        beat = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=50,
        )
        contrib = AggregateBeatContributionFactory(beat=beat, era=era)

        self.assertEqual(contrib.era, era)

    def test_manager_total_for_beat_sums_contributions(self) -> None:
        """total_for_beat aggregates all points for a beat (10 + 20 + 30 = 60)."""
        beat = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )
        AggregateBeatContributionFactory(beat=beat, points=10)
        AggregateBeatContributionFactory(beat=beat, points=20)
        AggregateBeatContributionFactory(beat=beat, points=30)

        total = AggregateBeatContribution.objects.total_for_beat(beat)

        self.assertEqual(total, 60)

    def test_manager_total_for_beat_returns_zero_for_no_contributions(self) -> None:
        """total_for_beat returns 0 when no contribution rows exist for the beat."""
        beat = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )

        total = AggregateBeatContribution.objects.total_for_beat(beat)

        self.assertEqual(total, 0)

    def test_manager_total_for_beat_only_sums_its_own_beat(self) -> None:
        """total_for_beat does not include contributions for other beats."""
        beat_a = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )
        beat_b = BeatFactory(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )
        AggregateBeatContributionFactory(beat=beat_a, points=40)
        AggregateBeatContributionFactory(beat=beat_b, points=99)

        self.assertEqual(AggregateBeatContribution.objects.total_for_beat(beat_a), 40)
        self.assertEqual(AggregateBeatContribution.objects.total_for_beat(beat_b), 99)

    def test_str_representation(self) -> None:
        """__str__ includes beat_id, character_sheet_id, and points."""
        contrib = AggregateBeatContributionFactory(points=15)
        result = str(contrib)
        self.assertIn(str(contrib.beat_id), result)
        self.assertIn("15", result)
