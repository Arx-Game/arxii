from django.core.exceptions import ValidationError
from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMTableFactory
from world.stories.constants import BeatOutcome, StoryScope
from world.stories.factories import (
    BeatCompletionFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    StoryFactory,
)


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


class BeatCompletionScopeCleanTests(EvenniaTestCase):
    """Tests for BeatCompletion.clean() scope-invariant enforcement."""

    def _make_beat_for_scope(self, scope: str) -> "Beat":
        story = StoryFactory(scope=scope)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        return BeatFactory(episode=episode)

    def test_clean_character_scope_requires_character_sheet(self) -> None:
        """CHARACTER-scope BeatCompletion must have character_sheet."""
        beat = self._make_beat_for_scope(StoryScope.CHARACTER)
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=None,
            gm_table=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("character_sheet", ctx.exception.message_dict)

    def test_clean_character_scope_rejects_gm_table(self) -> None:
        """CHARACTER-scope BeatCompletion must not have gm_table."""
        beat = self._make_beat_for_scope(StoryScope.CHARACTER)
        gm_table = GMTableFactory()
        sheet = CharacterSheetFactory()
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=sheet,
            gm_table=gm_table,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("gm_table", ctx.exception.message_dict)

    def test_clean_group_scope_requires_gm_table(self) -> None:
        """GROUP-scope BeatCompletion must have gm_table."""
        beat = self._make_beat_for_scope(StoryScope.GROUP)
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=None,
            gm_table=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("gm_table", ctx.exception.message_dict)

    def test_clean_group_scope_rejects_character_sheet(self) -> None:
        """GROUP-scope BeatCompletion must not have character_sheet."""
        beat = self._make_beat_for_scope(StoryScope.GROUP)
        gm_table = GMTableFactory()
        sheet = CharacterSheetFactory()
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=sheet,
            gm_table=gm_table,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("character_sheet", ctx.exception.message_dict)

    def test_clean_global_scope_rejects_character_sheet(self) -> None:
        """GLOBAL-scope BeatCompletion must not have character_sheet."""
        beat = self._make_beat_for_scope(StoryScope.GLOBAL)
        sheet = CharacterSheetFactory()
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=sheet,
            gm_table=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("character_sheet", ctx.exception.message_dict)

    def test_clean_global_scope_rejects_gm_table(self) -> None:
        """GLOBAL-scope BeatCompletion must not have gm_table."""
        beat = self._make_beat_for_scope(StoryScope.GLOBAL)
        gm_table = GMTableFactory()
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=None,
            gm_table=gm_table,
        )
        with self.assertRaises(ValidationError) as ctx:
            completion.clean()
        self.assertIn("gm_table", ctx.exception.message_dict)

    def test_clean_global_scope_both_null_passes(self) -> None:
        """GLOBAL-scope BeatCompletion with both FKs null passes clean()."""
        beat = self._make_beat_for_scope(StoryScope.GLOBAL)
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=None,
            gm_table=None,
        )
        # Should not raise.
        completion.clean()

    def test_clean_group_scope_gm_table_only_passes(self) -> None:
        """GROUP-scope BeatCompletion with gm_table only passes clean()."""
        beat = self._make_beat_for_scope(StoryScope.GROUP)
        gm_table = GMTableFactory()
        completion = BeatCompletionFactory.build(
            beat=beat,
            character_sheet=None,
            gm_table=gm_table,
        )
        # Should not raise.
        completion.clean()
