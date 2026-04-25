"""End-to-end integration test for Phase 3.

Scenario: a character has active stories across all three scopes. Various
mutations fire through the Wave 3 external hooks; auto-beats flip; the
Wave 4 internal cascade fans out to STORY_AT_MILESTONE beats; narrative
messages are emitted and delivered online vs queued offline; Wave 7
login catch-up drains the queue.

This test covers the full Phase 3 surface as a single ordered scenario.
Per-hook unit tests live in their respective test files.
"""

from unittest import mock

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.narrative.services import send_narrative_message
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StoryMilestoneType,
    StoryScope,
    TransitionMode,
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
    TransitionFactory,
)
from world.stories.services.episodes import resolve_episode
from world.stories.services.login import catch_up_character_stories


class Phase3EndToEndTests(EvenniaTestCase):
    """Full-system walkthrough: offline mutation → login catch-up → advance →
    cascade → narrative fan-out → offline queue → next login delivers."""

    def test_phase3_end_to_end_scenario(self) -> None:  # noqa: PLR0915 — single E2E walkthrough
        # ---- Arrange: Crucible with stories across all three scopes. ----
        crucible_sheet = CharacterSheetFactory()
        crucible_persona = PersonaFactory(character_sheet=crucible_sheet)

        # CHARACTER-scope story for Crucible.
        char_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=crucible_sheet,
        )
        char_chapter1 = ChapterFactory(story=char_story, order=1)
        char_chapter2 = ChapterFactory(story=char_story, order=2)
        char_ep1 = EpisodeFactory(chapter=char_chapter1)
        char_ep2 = EpisodeFactory(chapter=char_chapter2)
        TransitionFactory(
            source_episode=char_ep1,
            target_episode=char_ep2,
            mode=TransitionMode.AUTO,
            connection_summary="Therefore, you advance to chapter 2.",
        )
        defender_achievement = AchievementFactory(slug="defender")
        char_beat = BeatFactory(
            episode=char_ep1,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=defender_achievement,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="You prove yourself a true defender.",
        )
        char_progress = StoryProgressFactory(
            story=char_story,
            character_sheet=crucible_sheet,
            current_episode=char_ep1,
        )

        # GROUP-scope story for a covenant Crucible belongs to.
        covenant_table = GMTableFactory()
        GMTableMembershipFactory(table=covenant_table, persona=crucible_persona)
        group_story = StoryFactory(scope=StoryScope.GROUP, character_sheet=None)
        group_chapter = ChapterFactory(story=group_story)
        group_episode = EpisodeFactory(chapter=group_chapter)
        scarred_condition = ConditionTemplateFactory()
        group_beat = BeatFactory(
            episode=group_episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=scarred_condition,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="One of you bears the scars of the ordeal.",
        )
        GroupStoryProgressFactory(
            story=group_story,
            gm_table=covenant_table,
            current_episode=group_episode,
        )

        # GLOBAL-scope story gated on the CHARACTER-scope advancing to ch2.
        global_story = StoryFactory(scope=StoryScope.GLOBAL, character_sheet=None)
        global_chapter = ChapterFactory(story=global_story)
        global_episode = EpisodeFactory(chapter=global_chapter)
        StoryParticipationFactory(
            story=global_story,
            character=crucible_sheet.character,
        )
        global_beat = BeatFactory(
            episode=global_episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=char_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=char_chapter2,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="The world turns — Crucible ascends.",
        )
        GlobalStoryProgressFactory(
            story=global_story,
            current_episode=global_episode,
        )

        # ---- Act 1: Offline achievement grant (simulated via direct factory
        # insertion) — no Wave 3 hook fires. Beat stays UNSATISFIED. ----
        from world.achievements.factories import CharacterAchievementFactory

        CharacterAchievementFactory(
            character_sheet=crucible_sheet,
            achievement=defender_achievement,
        )
        # The beat must still be UNSATISFIED because no hook fired.
        char_beat.refresh_from_db()
        self.assertEqual(char_beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertEqual(
            NarrativeMessage.objects.filter(related_story=char_story).count(),
            0,
        )

        # ---- Act 2: Crucible puppets in. at_post_puppet fires the login
        # catch-up hook, which re-evaluates active stories and delivers
        # queued messages. The character-scope beat flips (CHARACTER) and
        # the group-scope beat stays UNSATISFIED (no condition yet). ----
        fake_session = mock.Mock()
        character = crucible_sheet.character
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg"),
        ):
            catch_up_character_stories(character)

        char_beat.refresh_from_db()
        self.assertEqual(char_beat.outcome, BeatOutcome.SUCCESS)
        # Character beat generated a narrative message delivered to Crucible.
        delivery = NarrativeMessageDelivery.objects.get(
            recipient_character_sheet=crucible_sheet,
            message__related_beat_completion__beat=char_beat,
        )
        self.assertIsNotNone(delivery.delivered_at)

        # ---- Act 3: Condition applied to Crucible via service call.
        # Wave 3 hook fires; Wave 5 ANY-member semantics flip the group beat. ----
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg"),
        ):
            apply_condition(character, scarred_condition)

        group_beat.refresh_from_db()
        self.assertEqual(group_beat.outcome, BeatOutcome.SUCCESS)

        # ---- Act 4: CHARACTER-scope story advances to ch2 via resolve_episode.
        # The Wave 4 internal cascade re-evaluates STORY_AT_MILESTONE beats
        # referencing char_story. The GLOBAL-scope global_beat flips. ----
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg"),
        ):
            resolve_episode(progress=char_progress)

        global_beat.refresh_from_db()
        self.assertEqual(global_beat.outcome, BeatOutcome.SUCCESS)

        # Narrative messages: char-beat completion, group-beat completion,
        # global-beat completion, plus an episode-resolution message for
        # the character-scope story.
        related_to_stories = NarrativeMessage.objects.filter(
            category=NarrativeCategory.STORY,
        )
        self.assertGreaterEqual(related_to_stories.count(), 4)

        # ---- Act 5: GM sends an ATMOSPHERE message while Crucible is online. ----
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg") as live_msg,
        ):
            atmos_msg = send_narrative_message(
                recipients=[crucible_sheet],
                body="Dark clouds gather over the city.",
                category=NarrativeCategory.ATMOSPHERE,
            )
        atmos_delivery = atmos_msg.deliveries.get(recipient_character_sheet=crucible_sheet)
        self.assertIsNotNone(atmos_delivery.delivered_at)
        live_msg.assert_called()

        # ---- Act 6: Crucible logs off. GM sends another message — goes to
        # queue. Next login delivers it. ----
        offline_msg = send_narrative_message(
            recipients=[crucible_sheet],
            body="A courier seeks your audience.",
            category=NarrativeCategory.HAPPENSTANCE,
        )
        offline_delivery = offline_msg.deliveries.get(recipient_character_sheet=crucible_sheet)
        self.assertIsNone(offline_delivery.delivered_at)  # queued offline

        # Crucible logs back in.
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg") as relogin_msg,
        ):
            catch_up_character_stories(character)

        offline_delivery.refresh_from_db()
        self.assertIsNotNone(offline_delivery.delivered_at)
        relogin_msg.assert_called()
