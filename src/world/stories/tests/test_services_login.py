"""Tests for Wave 7 — login catch-up hook.

catch_up_character_stories re-evaluates auto-beats across the
character's active stories and delivers any queued narrative messages.
"""

from unittest import mock

from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.factories import NarrativeMessageDeliveryFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.login import catch_up_character_stories


class LoginCatchupStoriesTests(EvenniaTestCase):
    def test_flips_auto_beat_on_login(self) -> None:
        """A character gained an achievement offline (no hook fired);
        login catch-up re-evaluates and flips the beat."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # Simulate offline grant — achievement row created directly,
        # bypassing grant_achievement to avoid the reactivity hook firing
        # now.
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)

        catch_up_character_stories(sheet.character)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_delivers_queued_messages(self) -> None:
        """Queued NarrativeMessageDeliveries get delivered_at set on login."""
        sheet = CharacterSheetFactory()
        delivery = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet,
            delivered_at=None,
        )
        fake_session = mock.Mock()
        character = sheet.character
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg") as msg_mock,
        ):
            catch_up_character_stories(character)

        delivery.refresh_from_db()
        self.assertIsNotNone(delivery.delivered_at)
        msg_mock.assert_called_once()

    def test_already_delivered_messages_unchanged(self) -> None:
        sheet = CharacterSheetFactory()
        earlier = timezone.now()
        delivery = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet,
            delivered_at=earlier,
        )
        fake_session = mock.Mock()
        character = sheet.character
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg"),
        ):
            catch_up_character_stories(character)
        delivery.refresh_from_db()
        self.assertEqual(delivery.delivered_at, earlier)

    def test_character_without_sheet_is_noop(self) -> None:
        """An NPC character without a CharacterSheet is safely skipped."""
        from evennia_extensions.factories import CharacterFactory

        npc = CharacterFactory()
        # No sheet_data — this should not raise.
        catch_up_character_stories(npc)
