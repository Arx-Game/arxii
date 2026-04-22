"""Tests for world.stories.services.beats."""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus
from world.stories.exceptions import BeatNotResolvableError
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.stories.services.beats import evaluate_auto_beats, record_gm_marked_outcome


class EvaluateAutoBeatsLevelTests(EvenniaTestCase):
    """Tests for CHARACTER_LEVEL_AT_LEAST predicate evaluation."""

    def _make_progress_with_sheet(self):
        """Return a StoryProgress whose character has no class assignments."""
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        return (
            StoryProgressFactory(
                character_sheet=sheet,
                current_episode=episode,
            ),
            sheet,
            episode,
        )

    def test_character_level_beat_satisfied_when_level_meets_requirement(self):
        """Beat flips to SUCCESS and BeatCompletion row is created."""
        progress, sheet, episode = self._make_progress_with_sheet()
        # Give the character a class at level 5.
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=5)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists())

    def test_character_level_beat_unsatisfied_when_below(self):
        """Beat stays UNSATISFIED and no BeatCompletion row is created."""
        progress, sheet, episode = self._make_progress_with_sheet()
        # Character only at level 3, requirement is 5.
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=3)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())

    def test_gm_marked_beats_untouched_by_auto_eval(self):
        """GM_MARKED beats are not changed by evaluate_auto_beats."""
        progress, _sheet, episode = self._make_progress_with_sheet()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())

    def test_evaluate_auto_beats_noop_when_no_current_episode(self):
        """No exception, no completions when progress.current_episode is None."""
        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=None)

        # Should not raise.
        evaluate_auto_beats(progress)

        self.assertFalse(BeatCompletion.objects.filter(character_sheet=sheet).exists())

    def test_evaluate_auto_beats_records_era(self):
        """BeatCompletion.era matches the active Era when one exists."""
        era = EraFactory(status=EraStatus.ACTIVE)
        progress, sheet, episode = self._make_progress_with_sheet()
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=5)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=1,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        completion = BeatCompletion.objects.get(beat=beat, character_sheet=sheet)
        self.assertEqual(completion.era, era)

    def test_evaluate_auto_beats_records_roster_entry(self):
        """BeatCompletion.roster_entry is populated when one exists for the sheet."""
        progress, sheet, episode = self._make_progress_with_sheet()
        roster = RosterFactory()
        entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=5)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=1,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        completion = BeatCompletion.objects.get(beat=beat, character_sheet=sheet)
        self.assertEqual(completion.roster_entry, entry)

    def test_evaluate_auto_beats_roster_entry_null_when_missing(self):
        """BeatCompletion.roster_entry is None when no RosterEntry exists."""
        progress, sheet, episode = self._make_progress_with_sheet()
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=5)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=1,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        completion = BeatCompletion.objects.get(beat=beat, character_sheet=sheet)
        self.assertIsNone(completion.roster_entry)


class RecordGmMarkedOutcomeTests(EvenniaTestCase):
    """Tests for record_gm_marked_outcome."""

    def _make_gm_beat_and_progress(self):
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=episode)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )
        return progress, beat, sheet

    def test_record_gm_marked_outcome_sets_outcome_and_creates_completion(self):
        """Happy path: outcome flipped, BeatCompletion created, row returned."""
        progress, beat, sheet = self._make_gm_beat_and_progress()

        completion = record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Test notes",
        )

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertIsInstance(completion, BeatCompletion)
        self.assertEqual(completion.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(completion.gm_notes, "Test notes")
        self.assertEqual(completion.character_sheet, sheet)

    def test_record_gm_marked_outcome_failure_path(self):
        """FAILURE is also a valid outcome for GM-marked beats."""
        progress, beat, _sheet = self._make_gm_beat_and_progress()

        completion = record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.FAILURE,
        )

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.FAILURE)
        self.assertEqual(completion.outcome, BeatOutcome.FAILURE)

    def test_record_gm_marked_outcome_rejects_non_gm_marked_beat(self):
        """BeatNotResolvableError raised when beat is CHARACTER_LEVEL_AT_LEAST."""
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=episode)
        level_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
        )

        with self.assertRaises(BeatNotResolvableError):
            record_gm_marked_outcome(
                progress=progress,
                beat=level_beat,
                outcome=BeatOutcome.SUCCESS,
            )

    def test_record_gm_marked_outcome_rejects_invalid_outcome(self):
        """BeatNotResolvableError raised for UNSATISFIED, EXPIRED, PENDING_GM_REVIEW."""
        progress, beat, _sheet = self._make_gm_beat_and_progress()

        for bad_outcome in (
            BeatOutcome.UNSATISFIED,
            BeatOutcome.EXPIRED,
            BeatOutcome.PENDING_GM_REVIEW,
        ):
            with self.subTest(outcome=bad_outcome):
                with self.assertRaises(BeatNotResolvableError):
                    record_gm_marked_outcome(
                        progress=progress,
                        beat=beat,
                        outcome=bad_outcome,
                    )


class EvaluateAutoBeatsIdempotencyTests(EvenniaTestCase):
    """Tests for evaluate_auto_beats idempotency — second call must not duplicate."""

    def test_evaluate_auto_beats_idempotent_does_not_duplicate_completions(self) -> None:
        """Calling evaluate_auto_beats twice creates exactly one BeatCompletion."""
        sheet = CharacterSheetFactory()
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=5)
        episode = EpisodeFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
        )
        story = StoryFactory(character_sheet=sheet)
        progress = StoryProgressFactory(
            character_sheet=sheet,
            current_episode=episode,
            story=story,
        )

        evaluate_auto_beats(progress)
        evaluate_auto_beats(progress)  # second call should be a no-op

        self.assertEqual(
            BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).count(),
            1,
        )
