"""Tests for world.stories.services.beats."""

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus, StoryMilestoneType
from world.stories.exceptions import BeatNotResolvableError
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.stories.services.beats import evaluate_auto_beats, record_gm_marked_outcome
from world.stories.types import StoryStatus


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


class EvaluateAutoBeatsAchievementTests(EvenniaTestCase):
    """Tests for ACHIEVEMENT_HELD predicate evaluation."""

    def _make_progress_with_sheet(self):
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        return (
            StoryProgressFactory(character_sheet=sheet, current_episode=episode),
            sheet,
            episode,
        )

    def test_achievement_held_beat_satisfied_when_achievement_earned(self):
        """Beat flips to SUCCESS when the character holds the required achievement."""
        progress, sheet, episode = self._make_progress_with_sheet()
        achievement = AchievementFactory()
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists())

    def test_achievement_held_beat_unsatisfied_when_not_earned(self):
        """Beat stays UNSATISFIED when the character does not hold the achievement."""
        progress, _sheet, episode = self._make_progress_with_sheet()
        achievement = AchievementFactory()
        # Do NOT grant the achievement to the character.

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())

    def test_achievement_held_beat_unsatisfied_when_different_achievement_held(self):
        """Beat stays UNSATISFIED when a different achievement is held."""
        progress, sheet, episode = self._make_progress_with_sheet()
        required_achievement = AchievementFactory()
        other_achievement = AchievementFactory()
        CharacterAchievementFactory(character_sheet=sheet, achievement=other_achievement)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=required_achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class EvaluateAutoBeatsConditionTests(EvenniaTestCase):
    """Tests for CONDITION_HELD predicate evaluation."""

    def _make_progress_with_sheet(self):
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        return (
            StoryProgressFactory(character_sheet=sheet, current_episode=episode),
            sheet,
            episode,
        )

    def test_condition_held_beat_satisfied_when_condition_active(self):
        """Beat flips to SUCCESS when the required condition is active on the character."""
        progress, sheet, episode = self._make_progress_with_sheet()
        template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet.character, condition=template)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists())

    def test_condition_held_beat_unsatisfied_when_not_active(self):
        """Beat stays UNSATISFIED when the required condition is not active."""
        progress, _sheet, episode = self._make_progress_with_sheet()
        template = ConditionTemplateFactory()

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())

    def test_condition_held_beat_unsatisfied_when_condition_is_suppressed(self):
        """Beat stays UNSATISFIED when the condition instance is suppressed."""
        progress, sheet, episode = self._make_progress_with_sheet()
        template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet.character, condition=template, is_suppressed=True)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_condition_held_beat_unsatisfied_when_different_condition_held(self):
        """Beat stays UNSATISFIED when a different condition is active."""
        progress, sheet, episode = self._make_progress_with_sheet()
        required_template = ConditionTemplateFactory()
        other_template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet.character, condition=other_template)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=required_template,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class EvaluateAutoBeatsCodexTests(EvenniaTestCase):
    """Tests for CODEX_ENTRY_UNLOCKED predicate evaluation."""

    def _make_progress_with_sheet_and_roster(self):
        sheet = CharacterSheetFactory()
        roster = RosterFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        episode = EpisodeFactory()
        return (
            StoryProgressFactory(character_sheet=sheet, current_episode=episode),
            sheet,
            roster_entry,
            episode,
        )

    def test_codex_entry_unlocked_beat_satisfied_when_entry_known(self):
        """Beat flips to SUCCESS when the character has KNOWN status for the entry."""
        progress, _sheet, roster_entry, episode = self._make_progress_with_sheet_and_roster()
        entry = CodexEntryFactory()
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=entry,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_codex_entry_unlocked_beat_unsatisfied_when_entry_uncovered(self):
        """Beat stays UNSATISFIED when the character only has UNCOVERED status."""
        progress, _sheet, roster_entry, episode = self._make_progress_with_sheet_and_roster()
        entry = CodexEntryFactory()
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=entry,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_codex_entry_unlocked_beat_unsatisfied_when_no_roster_entry(self):
        """Beat stays UNSATISFIED when the character sheet has no RosterEntry."""
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=episode)
        entry = CodexEntryFactory()

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=entry,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_codex_entry_unlocked_beat_unsatisfied_when_different_entry_known(self):
        """Beat stays UNSATISFIED when a different codex entry is known."""
        progress, _sheet, roster_entry, episode = self._make_progress_with_sheet_and_roster()
        required_entry = CodexEntryFactory()
        other_entry = CodexEntryFactory()
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=other_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=required_entry,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class EvaluateAutoBeatsStoryMilestoneTests(EvenniaTestCase):
    """Tests for STORY_AT_MILESTONE predicate evaluation.

    The referenced story is a CHARACTER-scope story with its own StoryProgress.
    The beat itself lives in a separate (unrelated) story's episode.
    """

    def _make_beat_progress(self):
        """Return a progress record for the beat's own story (not the referenced story)."""
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=episode)
        return progress, episode

    # --- STORY_RESOLVED ---

    def test_story_resolved_satisfied_when_story_completed(self):
        progress, episode = self._make_beat_progress()
        ref_story = StoryFactory(status=StoryStatus.COMPLETED)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_story_resolved_unsatisfied_when_story_active(self):
        progress, episode = self._make_beat_progress()
        ref_story = StoryFactory(status=StoryStatus.ACTIVE)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    # --- CHAPTER_REACHED ---

    def _make_character_story_at_chapter(self, chapter_order: int):
        """Create a CHARACTER-scope story with StoryProgress at chapter_order."""
        ref_sheet = CharacterSheetFactory()
        ref_story = StoryFactory(character_sheet=ref_sheet)
        ref_chapter = ChapterFactory(story=ref_story, order=chapter_order)
        ref_episode = EpisodeFactory(chapter=ref_chapter, order=1)
        StoryProgressFactory(
            story=ref_story,
            character_sheet=ref_sheet,
            current_episode=ref_episode,
        )
        return ref_story, ref_chapter

    def test_chapter_reached_satisfied_when_at_exact_chapter(self):
        progress, episode = self._make_beat_progress()
        # The chapter used as the current position IS the required chapter.
        ref_story, current_chapter = self._make_character_story_at_chapter(chapter_order=2)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=current_chapter,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_chapter_reached_satisfied_when_past_required_chapter(self):
        progress, episode = self._make_beat_progress()
        ref_story, _ref_chapter = self._make_character_story_at_chapter(chapter_order=3)
        earlier_chapter = ChapterFactory(story=ref_story, order=1)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=earlier_chapter,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_chapter_reached_unsatisfied_when_before_required_chapter(self):
        progress, episode = self._make_beat_progress()
        ref_story, _ref_chapter = self._make_character_story_at_chapter(chapter_order=1)
        future_chapter = ChapterFactory(story=ref_story, order=3)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=future_chapter,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_chapter_reached_unsatisfied_when_no_active_progress(self):
        progress, episode = self._make_beat_progress()
        ref_story = StoryFactory()
        ref_chapter = ChapterFactory(story=ref_story, order=1)
        # No StoryProgress created for ref_story.

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=ref_chapter,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    # --- EPISODE_REACHED ---

    def _make_story_at_episode(self, chapter_order: int, episode_order: int):
        """Create a CHARACTER-scope story with StoryProgress at specific chapter/episode."""
        ref_sheet = CharacterSheetFactory()
        ref_story = StoryFactory(character_sheet=ref_sheet)
        ref_chapter = ChapterFactory(story=ref_story, order=chapter_order)
        ref_episode = EpisodeFactory(chapter=ref_chapter, order=episode_order)
        StoryProgressFactory(
            story=ref_story,
            character_sheet=ref_sheet,
            current_episode=ref_episode,
        )
        return ref_story, ref_chapter, ref_episode

    def test_episode_reached_satisfied_when_at_exact_episode(self):
        progress, episode = self._make_beat_progress()
        ref_story, _ch, ref_ep = self._make_story_at_episode(chapter_order=2, episode_order=3)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=ref_ep,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_episode_reached_satisfied_when_in_later_chapter(self):
        progress, episode = self._make_beat_progress()
        ref_story, _ch, _current_ep = self._make_story_at_episode(chapter_order=3, episode_order=1)
        # Required episode is in an earlier chapter.
        earlier_chapter = ChapterFactory(story=ref_story, order=1)
        required_ep = EpisodeFactory(chapter=earlier_chapter, order=5)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=required_ep,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_episode_reached_unsatisfied_when_in_future_episode_same_chapter(self):
        progress, episode = self._make_beat_progress()
        ref_story, ref_chapter, _current_ep = self._make_story_at_episode(
            chapter_order=1, episode_order=2
        )
        future_ep = EpisodeFactory(chapter=ref_chapter, order=5)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=future_ep,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_episode_reached_unsatisfied_when_in_future_chapter(self):
        progress, episode = self._make_beat_progress()
        ref_story, _ch, _current_ep = self._make_story_at_episode(chapter_order=1, episode_order=3)
        future_chapter = ChapterFactory(story=ref_story, order=3)
        future_ep = EpisodeFactory(chapter=future_chapter, order=1)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=future_ep,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


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
