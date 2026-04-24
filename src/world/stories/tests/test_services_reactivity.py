"""Tests for world.stories.services.reactivity.

Covers the five external entry points (on_character_level_changed,
on_achievement_earned, on_condition_applied, on_condition_expired,
on_codex_entry_unlocked) and the internal on_story_advanced cascade
entry point used by resolve_episode.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.stories.services.reactivity import (
    on_achievement_earned,
    on_character_level_changed,
    on_codex_entry_unlocked,
    on_condition_applied,
    on_condition_expired,
    on_story_advanced,
)


class OnCharacterLevelChangedTests(EvenniaTestCase):
    def test_reevaluates_character_scope_level_beat(self) -> None:
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        progress = StoryProgressFactory(
            character_sheet=sheet,
            story=episode.chapter.story,
            current_episode=episode,
        )
        # Update the story scope and owner for CHARACTER scope to validate.
        progress.story.scope = StoryScope.CHARACTER
        progress.story.character_sheet = sheet
        progress.story.save()

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=3,
            outcome=BeatOutcome.UNSATISFIED,
        )
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=sheet.character,
            character_class=char_class,
            level=3,
        )
        # Sheet's cached_property was already materialised in factory setup —
        # the hook should invalidate it and re-evaluate successfully.
        on_character_level_changed(sheet)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(
            BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists(),
        )

    def test_noop_when_no_active_progress(self) -> None:
        sheet = CharacterSheetFactory()
        # No stories attached — should execute without error.
        on_character_level_changed(sheet)


class OnAchievementEarnedTests(EvenniaTestCase):
    def test_reevaluates_group_scope_achievement_beat(self) -> None:
        # Group progress the sheet belongs to through active membership.
        sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        story = StoryFactory(scope=StoryScope.GROUP, character_sheet=None)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        GroupStoryProgressFactory(
            story=story,
            gm_table=table,
            current_episode=episode,
        )

        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # Member earns the achievement — Wave 5 (ANY-member) is required
        # for the GROUP flip, so this test only verifies the reactivity
        # entry point executes without error and completes its cache
        # invalidation step.
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)
        on_achievement_earned(sheet, achievement)
        beat.refresh_from_db()
        # Wave 2: GROUP-scope achievement beats stay UNSATISFIED; Wave 5
        # will flip them.
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_invalidates_achievement_cache(self) -> None:
        sheet = CharacterSheetFactory()
        achievement = AchievementFactory()
        # Warm the cache.
        _ = sheet.cached_achievements_held
        # Add the achievement behind the cache.
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)
        on_achievement_earned(sheet, achievement)
        # Cache should have been invalidated and re-populated.
        self.assertIn(achievement, sheet.cached_achievements_held)


class OnConditionAppliedTests(EvenniaTestCase):
    def test_reevaluates_character_scope_condition_beat(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )
        instance = ConditionInstanceFactory(target=sheet.character, condition=template)
        on_condition_applied(sheet, instance)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class OnConditionExpiredTests(EvenniaTestCase):
    def test_does_not_reflip_satisfied_beat(self) -> None:
        """on_condition_expired runs without error and doesn't un-flip SUCCESS."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.SUCCESS,
        )
        on_condition_expired(sheet, template)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class OnCodexEntryUnlockedTests(EvenniaTestCase):
    def test_reevaluates_character_scope_codex_beat(self) -> None:
        roster = RosterFactory()
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        codex_entry = CodexEntryFactory()

        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        on_codex_entry_unlocked(sheet, codex_entry)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class OnStoryAdvancedCascadeTests(EvenniaTestCase):
    def test_cascade_reevaluates_beats_referencing_advanced_story(self) -> None:
        """A STORY_AT_MILESTONE beat whose referenced_story has advanced to the
        required chapter flips to SUCCESS."""
        from world.stories.constants import StoryMilestoneType

        referenced_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=None)
        # Build two chapters on referenced_story (ch1 establishes the
        # "already advanced" ordering; ch2 is the target the beat cares about).
        ChapterFactory(story=referenced_story, order=1)
        ref_ch2 = ChapterFactory(story=referenced_story, order=2)
        # Set the referenced story to already sit on chapter 2 (advanced).
        ref_ep2 = EpisodeFactory(chapter=ref_ch2)
        referenced_sheet = CharacterSheetFactory()
        referenced_story.character_sheet = referenced_sheet
        referenced_story.save()
        StoryProgressFactory(
            story=referenced_story,
            character_sheet=referenced_sheet,
            current_episode=ref_ep2,
        )

        # Build the gated story with a STORY_AT_MILESTONE beat.
        gated_sheet = CharacterSheetFactory()
        gated_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=gated_sheet)
        gated_episode = EpisodeFactory(chapter=ChapterFactory(story=gated_story))
        StoryProgressFactory(
            story=gated_story,
            character_sheet=gated_sheet,
            current_episode=gated_episode,
        )
        beat = BeatFactory(
            episode=gated_episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=referenced_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=ref_ch2,
            outcome=BeatOutcome.UNSATISFIED,
        )

        on_story_advanced(referenced_story)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_cascade_skips_progress_not_on_referenced_episode(self) -> None:
        """Beats whose episode doesn't match current_episode of active
        progress are not re-evaluated."""
        from world.stories.constants import StoryMilestoneType

        referenced_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=None)
        ref_ch = ChapterFactory(story=referenced_story, order=1)

        gated_sheet = CharacterSheetFactory()
        gated_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=gated_sheet)
        gated_ch = ChapterFactory(story=gated_story)
        beat_episode = EpisodeFactory(chapter=gated_ch, order=1)
        current_episode = EpisodeFactory(chapter=gated_ch, order=2)
        StoryProgressFactory(
            story=gated_story,
            character_sheet=gated_sheet,
            current_episode=current_episode,
        )

        beat = BeatFactory(
            episode=beat_episode,  # progress is NOT on this episode
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=referenced_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=ref_ch,
            outcome=BeatOutcome.UNSATISFIED,
        )

        on_story_advanced(referenced_story)

        beat.refresh_from_db()
        # Beat not re-evaluated because no progress sits on its episode.
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class HookIdempotencyTests(EvenniaTestCase):
    def test_double_call_does_not_duplicate_beat_completions(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        achievement = AchievementFactory()
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)
        on_achievement_earned(sheet, achievement)
        first_count = BeatCompletion.objects.count()
        on_achievement_earned(sheet, achievement)
        second_count = BeatCompletion.objects.count()
        self.assertEqual(first_count, second_count)


class GlobalScopeProgressIterationTests(EvenniaTestCase):
    def test_global_progress_picked_up_via_participation(self) -> None:
        """Hook walks through StoryParticipation → GlobalStoryProgress."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.GLOBAL, character_sheet=None)
        StoryParticipationFactory(story=story, character=sheet.character)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        GlobalStoryProgressFactory(story=story, current_episode=episode)

        from world.stories.constants import StoryMilestoneType

        ref_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=None)
        ref_ch = ChapterFactory(story=ref_story, order=1)
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=ref_ch,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # Simply verify no error walking the iteration — this exercises
        # the GLOBAL branch of _active_progress_for_character.
        on_character_level_changed(sheet)
