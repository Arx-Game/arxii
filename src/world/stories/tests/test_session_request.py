"""Tests for the SessionRequest model (Wave 7, Task 7.1)."""

from django.test import TestCase

from world.stories.constants import SessionRequestStatus
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    SessionRequestFactory,
    StoryFactory,
)
from world.stories.models import SessionRequest


class SessionRequestCreationTest(TestCase):
    """SessionRequest model creation and round-trip."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

    def test_create_session_request_defaults(self) -> None:
        """A freshly created SessionRequest has expected defaults."""
        sr = SessionRequestFactory(episode=self.episode)
        self.assertEqual(sr.status, SessionRequestStatus.OPEN)
        self.assertIsNone(sr.event)
        self.assertFalse(sr.open_to_any_gm)
        self.assertIsNone(sr.assigned_gm)
        self.assertIsNone(sr.initiated_by_account)
        self.assertEqual(sr.notes, "")

    def test_round_trip(self) -> None:
        """SessionRequest can be saved and retrieved from the database."""
        sr = SessionRequestFactory(episode=self.episode)
        fetched = SessionRequest.objects.get(pk=sr.pk)
        self.assertEqual(fetched.episode_id, self.episode.pk)
        self.assertEqual(fetched.status, SessionRequestStatus.OPEN)

    def test_timestamps_set_on_create(self) -> None:
        """created_at and updated_at are populated on creation."""
        sr = SessionRequestFactory(episode=self.episode)
        self.assertIsNotNone(sr.created_at)
        self.assertIsNotNone(sr.updated_at)

    def test_str(self) -> None:
        """__str__ includes episode title and status."""
        sr = SessionRequestFactory(episode=self.episode)
        result = str(sr)
        self.assertIn(self.episode.title, result)
        self.assertIn("open", result)

    def test_event_fk_null_at_creation(self) -> None:
        """event FK is null when a SessionRequest is first created."""
        sr = SessionRequestFactory(episode=self.episode)
        self.assertIsNone(sr.event_id)


class SessionRequestStatusTransitionTest(TestCase):
    """Status transitions via direct .save() calls."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

    def test_transition_open_to_scheduled(self) -> None:
        """Status can be moved from OPEN to SCHEDULED and persisted."""
        sr = SessionRequestFactory(episode=self.episode)
        sr.status = SessionRequestStatus.SCHEDULED
        sr.save(update_fields=["status", "updated_at"])
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.SCHEDULED)

    def test_transition_scheduled_to_resolved(self) -> None:
        """Status can be moved from SCHEDULED to RESOLVED."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.SCHEDULED)
        sr.status = SessionRequestStatus.RESOLVED
        sr.save(update_fields=["status", "updated_at"])
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.RESOLVED)

    def test_transition_open_to_cancelled(self) -> None:
        """Status can be moved from OPEN to CANCELLED."""
        sr = SessionRequestFactory(episode=self.episode)
        sr.status = SessionRequestStatus.CANCELLED
        sr.save(update_fields=["status", "updated_at"])
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.CANCELLED)


class SessionRequestStoryPropertyTest(TestCase):
    """The story property walks episode -> chapter -> story correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

    def test_story_property_returns_correct_story(self) -> None:
        """sr.story walks episode.chapter.story and returns the right Story."""
        sr = SessionRequestFactory(episode=self.episode)
        self.assertEqual(sr.story.pk, self.story.pk)
        self.assertEqual(sr.story.title, self.story.title)

    def test_story_property_for_nested_episode(self) -> None:
        """story property works for episodes in any chapter order."""
        chapter2 = ChapterFactory(story=self.story, order=2)
        episode2 = EpisodeFactory(chapter=chapter2, order=1)
        sr = SessionRequestFactory(episode=episode2)
        self.assertEqual(sr.story.pk, self.story.pk)

    def test_story_property_for_different_story(self) -> None:
        """Different episodes in different stories return the right story each."""
        story_b = StoryFactory()
        chapter_b = ChapterFactory(story=story_b, order=1)
        episode_b = EpisodeFactory(chapter=chapter_b, order=1)

        sr_a = SessionRequestFactory(episode=self.episode)
        sr_b = SessionRequestFactory(episode=episode_b)

        self.assertEqual(sr_a.story.pk, self.story.pk)
        self.assertEqual(sr_b.story.pk, story_b.pk)
        self.assertNotEqual(sr_a.story.pk, sr_b.story.pk)


class SessionRequestIndexQueryTest(TestCase):
    """Verify that indexed query patterns work correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

    def test_filter_by_status(self) -> None:
        """Can filter SessionRequests by status."""
        SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)
        SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.CANCELLED)

        open_qs = SessionRequest.objects.filter(status=SessionRequestStatus.OPEN)
        self.assertEqual(open_qs.count(), 1)

    def test_filter_by_episode_and_status(self) -> None:
        """Can filter by episode + status (indexed path)."""
        other_episode = EpisodeFactory(chapter=self.chapter, order=2)
        SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)
        SessionRequestFactory(episode=other_episode, status=SessionRequestStatus.OPEN)

        qs = SessionRequest.objects.filter(episode=self.episode, status=SessionRequestStatus.OPEN)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().episode_id, self.episode.pk)
