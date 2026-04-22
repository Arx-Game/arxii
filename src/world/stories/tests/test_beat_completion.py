from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from world.stories.constants import BeatOutcome
from world.stories.factories import BeatCompletionFactory, EraFactory


class BeatCompletionModelTests(EvenniaTestCase):
    """Unit tests for the BeatCompletion audit ledger model."""

    def test_completion_records_outcome_and_character(self) -> None:
        """BeatCompletion stores beat, character_sheet, outcome, and recorded_at."""
        completion = BeatCompletionFactory(outcome=BeatOutcome.SUCCESS)
        self.assertEqual(completion.outcome, BeatOutcome.SUCCESS)
        self.assertIsNotNone(completion.beat)
        self.assertIsNotNone(completion.character_sheet)
        self.assertIsNotNone(completion.recorded_at)
        self.assertLessEqual(completion.recorded_at, timezone.now())

    def test_completion_captures_era(self) -> None:
        """BeatCompletion correctly stores a supplied Era FK."""
        era = EraFactory()
        completion = BeatCompletionFactory(era=era)
        self.assertEqual(completion.era, era)

    def test_completion_defaults_roster_entry_and_era_to_none(self) -> None:
        """roster_entry and era are optional and default to None."""
        completion = BeatCompletionFactory()
        self.assertIsNone(completion.roster_entry)
        self.assertIsNone(completion.era)

    def test_completion_str(self) -> None:
        """__str__ includes beat_id, character_sheet_id, and outcome."""
        completion = BeatCompletionFactory(outcome=BeatOutcome.FAILURE)
        result = str(completion)
        self.assertIn(str(completion.beat_id), result)
        self.assertIn(str(completion.character_sheet_id), result)
        self.assertIn(BeatOutcome.FAILURE, result)
