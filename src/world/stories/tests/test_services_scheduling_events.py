"""Tests for world.stories.services.scheduling — Events bridging (Wave 7, Task 7.3).

Tests for create_event_from_session_request, cancel_session_request,
and resolve_session_request.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import SessionRequestStatus
from world.stories.exceptions import SessionRequestNotOpenError
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    SessionRequestFactory,
    StoryFactory,
)
from world.stories.services.scheduling import (
    cancel_session_request,
    create_event_from_session_request,
    resolve_session_request,
)


class CreateEventFromSessionRequestTests(TestCase):
    """Tests for the create_event_from_session_request bridge service."""

    @classmethod
    def setUpTestData(cls) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        cls.episode = EpisodeFactory(chapter=chapter, order=1)

    def _make_open_request(self):
        """Return a fresh OPEN SessionRequest (not shared between tests)."""
        return SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)

    def test_happy_path_creates_event_and_transitions_to_scheduled(self) -> None:
        """An OPEN SessionRequest is bridged to an Event; status becomes SCHEDULED."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = self._make_open_request()
        scheduled_time = timezone.now() + timedelta(days=3)

        event = create_event_from_session_request(
            session_request=sr,
            name="The Grand Session",
            scheduled_real_time=scheduled_time,
            host_persona=host,
            location_id=room.pk,
            description="A pivotal story session.",
        )

        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.SCHEDULED)
        self.assertIsNotNone(sr.event_id)
        self.assertEqual(sr.event_id, event.pk)
        self.assertEqual(event.name, "The Grand Session")

    def test_event_has_primary_host(self) -> None:
        """The created Event has an EventHost with is_primary=True for the host persona."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = self._make_open_request()
        scheduled_time = timezone.now() + timedelta(days=3)

        event = create_event_from_session_request(
            session_request=sr,
            name="Session with Host",
            scheduled_real_time=scheduled_time,
            host_persona=host,
            location_id=room.pk,
        )

        primary_hosts = list(event.hosts.filter(is_primary=True))
        self.assertEqual(len(primary_hosts), 1)
        self.assertEqual(primary_hosts[0].persona_id, host.pk)

    def test_raises_when_session_request_not_open(self) -> None:
        """Raises SessionRequestNotOpenError when the request is not OPEN."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.SCHEDULED)
        scheduled_time = timezone.now() + timedelta(days=3)

        with self.assertRaises(SessionRequestNotOpenError):
            create_event_from_session_request(
                session_request=sr,
                name="Should Fail",
                scheduled_real_time=scheduled_time,
                host_persona=host,
                location_id=room.pk,
            )

        # Status must be unchanged.
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.SCHEDULED)

    def test_raises_for_cancelled_request(self) -> None:
        """Raises SessionRequestNotOpenError when the request is CANCELLED."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.CANCELLED)
        scheduled_time = timezone.now() + timedelta(days=3)

        with self.assertRaises(SessionRequestNotOpenError):
            create_event_from_session_request(
                session_request=sr,
                name="Should Fail",
                scheduled_real_time=scheduled_time,
                host_persona=host,
                location_id=room.pk,
            )

    def test_raises_for_resolved_request(self) -> None:
        """Raises SessionRequestNotOpenError when the request is RESOLVED."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.RESOLVED)
        scheduled_time = timezone.now() + timedelta(days=3)

        with self.assertRaises(SessionRequestNotOpenError):
            create_event_from_session_request(
                session_request=sr,
                name="Should Fail",
                scheduled_real_time=scheduled_time,
                host_persona=host,
                location_id=room.pk,
            )

    def test_event_status_is_draft(self) -> None:
        """The created Event starts in DRAFT status (before the GM schedules it)."""
        room = RoomProfileFactory()
        host = PersonaFactory()
        sr = self._make_open_request()
        scheduled_time = timezone.now() + timedelta(days=3)

        event = create_event_from_session_request(
            session_request=sr,
            name="Draft Event Test",
            scheduled_real_time=scheduled_time,
            host_persona=host,
            location_id=room.pk,
        )

        self.assertEqual(event.status, EventStatus.DRAFT)


class CancelSessionRequestTests(TestCase):
    """Tests for cancel_session_request."""

    @classmethod
    def setUpTestData(cls) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        cls.episode = EpisodeFactory(chapter=chapter, order=1)

    def test_cancel_open_request(self) -> None:
        """An OPEN SessionRequest can be cancelled."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)
        result = cancel_session_request(session_request=sr)

        self.assertEqual(result.status, SessionRequestStatus.CANCELLED)
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.CANCELLED)

    def test_cancel_returns_the_request(self) -> None:
        """cancel_session_request returns the same SessionRequest instance."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)
        result = cancel_session_request(session_request=sr)
        self.assertEqual(result.pk, sr.pk)

    def test_cancel_already_cancelled_raises(self) -> None:
        """Cancelling an already-CANCELLED request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.CANCELLED)
        with self.assertRaises(SessionRequestNotOpenError):
            cancel_session_request(session_request=sr)

    def test_cancel_scheduled_raises(self) -> None:
        """Cancelling a SCHEDULED request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.SCHEDULED)
        with self.assertRaises(SessionRequestNotOpenError):
            cancel_session_request(session_request=sr)

    def test_cancel_resolved_raises(self) -> None:
        """Cancelling a RESOLVED request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.RESOLVED)
        with self.assertRaises(SessionRequestNotOpenError):
            cancel_session_request(session_request=sr)


class ResolveSessionRequestTests(TestCase):
    """Tests for resolve_session_request."""

    @classmethod
    def setUpTestData(cls) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        cls.episode = EpisodeFactory(chapter=chapter, order=1)

    def test_resolve_scheduled_request(self) -> None:
        """A SCHEDULED SessionRequest can be resolved after the session runs."""
        event = EventFactory()
        sr = SessionRequestFactory(
            episode=self.episode, status=SessionRequestStatus.SCHEDULED, event=event
        )
        result = resolve_session_request(session_request=sr)

        self.assertEqual(result.status, SessionRequestStatus.RESOLVED)
        sr.refresh_from_db()
        self.assertEqual(sr.status, SessionRequestStatus.RESOLVED)

    def test_resolve_returns_the_request(self) -> None:
        """resolve_session_request returns the same SessionRequest instance."""
        event = EventFactory()
        sr = SessionRequestFactory(
            episode=self.episode, status=SessionRequestStatus.SCHEDULED, event=event
        )
        result = resolve_session_request(session_request=sr)
        self.assertEqual(result.pk, sr.pk)

    def test_resolve_open_raises(self) -> None:
        """Resolving an OPEN (not yet scheduled) request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)
        with self.assertRaises(SessionRequestNotOpenError):
            resolve_session_request(session_request=sr)

    def test_resolve_already_resolved_raises(self) -> None:
        """Resolving an already-RESOLVED request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.RESOLVED)
        with self.assertRaises(SessionRequestNotOpenError):
            resolve_session_request(session_request=sr)

    def test_resolve_cancelled_raises(self) -> None:
        """Resolving a CANCELLED request raises SessionRequestNotOpenError."""
        sr = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.CANCELLED)
        with self.assertRaises(SessionRequestNotOpenError):
            resolve_session_request(session_request=sr)
