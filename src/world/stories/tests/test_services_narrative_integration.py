"""Tests for Wave 6 — stories → narrative integration.

BeatCompletion creation (via auto-eval, GM mark, or aggregate threshold)
and EpisodeResolution creation both emit NarrativeMessage deliveries to
scope-appropriate recipients.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
from world.stories.services.beats import (
    evaluate_auto_beats,
    record_aggregate_contribution,
    record_gm_marked_outcome,
)
from world.stories.services.episodes import resolve_episode


class AutoBeatCompletionNarrativeTests(EvenniaTestCase):
    def test_auto_flip_character_scope_emits_narrative_message(self) -> None:
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
            player_resolution_text="You prove yourself worthy.",
        )
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)

        progress = sheet.story_progress.first()
        evaluate_auto_beats(progress)

        messages = NarrativeMessage.objects.filter(
            category=NarrativeCategory.STORY,
            related_story=story,
        )
        self.assertEqual(messages.count(), 1)
        self.assertEqual(messages.first().body, "You prove yourself worthy.")

        deliveries = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=sheet,
        )
        self.assertEqual(deliveries.count(), 1)

    def test_auto_flip_uses_default_body_when_resolution_text_empty(self) -> None:
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
            player_resolution_text="",
        )
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)
        progress = sheet.story_progress.first()
        evaluate_auto_beats(progress)

        msg = NarrativeMessage.objects.get(related_story=story)
        self.assertIn("resolved", msg.body.lower())


class GMMarkedBeatNarrativeTests(EvenniaTestCase):
    def test_gm_marked_beat_emits_narrative_message(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        progress = StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="The GM marks the scene closed.",
        )

        record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Clean scene.",
        )

        messages = NarrativeMessage.objects.filter(
            category=NarrativeCategory.STORY,
            related_story=story,
        )
        self.assertEqual(messages.count(), 1)
        self.assertEqual(messages.first().body, "The GM marks the scene closed.")


class AggregateThresholdBeatNarrativeTests(EvenniaTestCase):
    def test_aggregate_threshold_crossing_emits_narrative_message(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=10,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="The campaign culminates in triumph.",
        )

        record_aggregate_contribution(
            beat=beat,
            character_sheet=sheet,
            points=10,
        )

        msgs = NarrativeMessage.objects.filter(related_story=story)
        self.assertEqual(msgs.count(), 1)
        self.assertEqual(msgs.first().body, "The campaign culminates in triumph.")

    def test_aggregate_partial_contribution_does_not_emit_message(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="Should not appear yet.",
        )

        # Partial contribution — beat stays UNSATISFIED.
        record_aggregate_contribution(beat=beat, character_sheet=sheet, points=25)
        self.assertEqual(NarrativeMessage.objects.filter(related_story=story).count(), 0)


class GroupScopeBeatNarrativeTests(EvenniaTestCase):
    def test_group_completion_fans_out_to_all_members(self) -> None:
        m1_sheet = CharacterSheetFactory()
        m2_sheet = CharacterSheetFactory()
        p1 = PersonaFactory(character_sheet=m1_sheet)
        p2 = PersonaFactory(character_sheet=m2_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=p1)
        GMTableMembershipFactory(table=table, persona=p2)
        story = StoryFactory(scope=StoryScope.GROUP, character_sheet=None)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        progress = GroupStoryProgressFactory(
            story=story,
            gm_table=table,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="The covenant's trial is resolved.",
        )

        record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
        )

        msgs = NarrativeMessage.objects.filter(related_story=story)
        self.assertEqual(msgs.count(), 1)
        deliveries = NarrativeMessageDelivery.objects.filter(message=msgs.first())
        self.assertEqual(deliveries.count(), 2)
        recipients = {d.recipient_character_sheet for d in deliveries}
        self.assertEqual(recipients, {m1_sheet, m2_sheet})


class EpisodeResolutionNarrativeTests(EvenniaTestCase):
    def test_resolve_episode_emits_narrative_message(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        source = EpisodeFactory(chapter=chapter)
        target = EpisodeFactory(chapter=chapter)
        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
            connection_summary="Therefore, the story advances.",
        )
        progress = StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=source,
        )

        resolution = resolve_episode(progress=progress)

        msg = NarrativeMessage.objects.get(related_episode_resolution=resolution)
        self.assertEqual(msg.body, "Therefore, the story advances.")
        self.assertEqual(msg.category, NarrativeCategory.STORY)

    def test_resolve_episode_falls_back_to_episode_summary(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        source = EpisodeFactory(chapter=chapter, summary="The scene closes.")
        target = EpisodeFactory(chapter=chapter)
        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
            connection_summary="",
        )
        progress = StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=source,
        )
        resolve_episode(progress=progress)

        msg = NarrativeMessage.objects.filter(related_story=story).first()
        self.assertEqual(msg.body, "The scene closes.")
