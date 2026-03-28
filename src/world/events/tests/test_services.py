"""Tests for event service functions."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.events.constants import EventStatus, InvitationTargetType
from world.events.factories import EventFactory, EventHostFactory, EventInvitationFactory
from world.events.models import EventModification
from world.events.services import (
    add_host,
    cancel_event,
    complete_event,
    create_event,
    get_visible_events,
    invite_organization,
    invite_persona,
    invite_society,
    schedule_event,
    set_room_description_overlay,
    start_event,
    validate_location_gap,
)
from world.events.types import EventError
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import PersonaFactory
from world.scenes.models import Scene
from world.societies.factories import OrganizationFactory, SocietyFactory


class ValidateLocationGapTest(TestCase):
    def test_available_slot(self) -> None:
        event = EventFactory()
        far_future = event.scheduled_real_time + timedelta(hours=12)
        result = validate_location_gap(event.location_id, far_future)
        self.assertTrue(result)

    def test_blocked_slot(self) -> None:
        event = EventFactory()
        nearby = event.scheduled_real_time + timedelta(hours=2)
        result = validate_location_gap(event.location_id, nearby)
        self.assertFalse(result)

    def test_cancelled_events_ignored(self) -> None:
        room = RoomProfileFactory()
        now = timezone.now() + timedelta(days=1)
        EventFactory(location=room, status=EventStatus.CANCELLED, scheduled_real_time=now)
        result = validate_location_gap(room.pk, now + timedelta(hours=1))
        self.assertTrue(result)

    def test_completed_events_ignored(self) -> None:
        room = RoomProfileFactory()
        now = timezone.now() + timedelta(days=1)
        EventFactory(location=room, status=EventStatus.COMPLETED, scheduled_real_time=now)
        result = validate_location_gap(room.pk, now + timedelta(hours=1))
        self.assertTrue(result)

    def test_exclude_self(self) -> None:
        event = EventFactory()
        result = validate_location_gap(
            event.location_id, event.scheduled_real_time, exclude_event_id=event.id
        )
        self.assertTrue(result)


class CreateEventTest(TestCase):
    def test_creates_event_with_primary_host(self) -> None:
        room = RoomProfileFactory()
        persona = PersonaFactory()
        event = create_event(
            name="Test Gathering",
            location_id=room.pk,
            scheduled_real_time=timezone.now() + timedelta(days=1),
            host_persona=persona,
        )
        self.assertEqual(event.name, "Test Gathering")
        self.assertEqual(event.status, EventStatus.DRAFT)
        self.assertTrue(event.hosts.filter(is_primary=True).exists())

    def test_rejects_conflicting_time_slot(self) -> None:
        existing = EventFactory()
        with self.assertRaises(EventError):
            create_event(
                name="Conflicting Event",
                location_id=existing.location_id,
                scheduled_real_time=existing.scheduled_real_time + timedelta(hours=1),
                host_persona=PersonaFactory(),
            )


class EventLifecycleTest(TestCase):
    def test_schedule_from_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        schedule_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.SCHEDULED)

    def test_schedule_from_non_draft_raises(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        with self.assertRaises(EventError):
            schedule_event(event)

    def test_start_from_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        start_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.ACTIVE)
        self.assertIsNotNone(event.started_at)

    def test_start_creates_linked_scene(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED, is_public=True)
        start_event(event)
        scene = Scene.objects.get(event=event)
        self.assertEqual(scene.name, event.name)
        self.assertEqual(scene.location_id, event.location.objectdb_id)
        self.assertTrue(scene.is_active)
        self.assertEqual(scene.privacy_mode, ScenePrivacyMode.PUBLIC)

    def test_start_private_event_creates_private_scene(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED, is_public=False)
        start_event(event)
        scene = Scene.objects.get(event=event)
        self.assertEqual(scene.privacy_mode, ScenePrivacyMode.PRIVATE)

    def test_start_already_active_raises(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        start_event(event)
        with self.assertRaises(EventError):
            start_event(event)

    def test_start_from_non_scheduled_raises(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        with self.assertRaises(EventError):
            start_event(event)

    def test_complete_from_active(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        complete_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.COMPLETED)
        self.assertIsNotNone(event.ended_at)

    def test_complete_finishes_linked_scene(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        start_event(event)
        scene = Scene.objects.get(event=event)
        self.assertTrue(scene.is_active)

        complete_event(event)
        scene.refresh_from_db()
        self.assertFalse(scene.is_active)
        self.assertIsNotNone(scene.date_finished)

    def test_complete_from_non_active_raises(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        with self.assertRaises(EventError):
            complete_event(event)

    def test_cancel_from_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        cancel_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_cancel_from_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        cancel_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_cancel_active_event_finishes_scene(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        start_event(event)
        scene = Scene.objects.get(event=event)
        self.assertTrue(scene.is_active)

        cancel_event(event)
        scene.refresh_from_db()
        self.assertFalse(scene.is_active)

    def test_cancel_completed_raises(self) -> None:
        event = EventFactory(status=EventStatus.COMPLETED)
        with self.assertRaises(EventError):
            cancel_event(event)

    def test_cancel_already_cancelled_raises(self) -> None:
        event = EventFactory(status=EventStatus.CANCELLED)
        with self.assertRaises(EventError):
            cancel_event(event)


class AddHostTest(TestCase):
    def test_add_host(self) -> None:
        event = EventFactory()
        persona = PersonaFactory()
        host = add_host(event, persona, is_primary=False)
        self.assertEqual(host.event, event)
        self.assertEqual(host.persona, persona)
        self.assertFalse(host.is_primary)


class InvitationTest(TestCase):
    def test_invite_persona(self) -> None:
        event = EventFactory()
        target = PersonaFactory()
        host = PersonaFactory()
        invitation = invite_persona(event, target, invited_by=host)
        self.assertEqual(invitation.target_type, InvitationTargetType.PERSONA)
        self.assertEqual(invitation.target_persona, target)
        self.assertEqual(invitation.invited_by, host)

    def test_invite_organization(self) -> None:
        event = EventFactory()
        org = OrganizationFactory()
        invitation = invite_organization(event, org)
        self.assertEqual(invitation.target_type, InvitationTargetType.ORGANIZATION)
        self.assertEqual(invitation.target_organization, org)

    def test_invite_society(self) -> None:
        event = EventFactory()
        society = SocietyFactory()
        invitation = invite_society(event, society)
        self.assertEqual(invitation.target_type, InvitationTargetType.SOCIETY)
        self.assertEqual(invitation.target_society, society)


class RoomDescriptionOverlayTest(TestCase):
    def test_set_overlay_creates_modification(self) -> None:
        event = EventFactory()
        mod = set_room_description_overlay(event, "Decorated with flowers.")
        self.assertEqual(mod.room_description_overlay, "Decorated with flowers.")

    def test_set_overlay_updates_existing(self) -> None:
        event = EventFactory()
        set_room_description_overlay(event, "First version.")
        mod = set_room_description_overlay(event, "Updated version.")
        self.assertEqual(mod.room_description_overlay, "Updated version.")
        self.assertEqual(EventModification.objects.filter(event=event).count(), 1)


class GetVisibleEventsTest(TestCase):
    def test_anonymous_sees_only_public(self) -> None:
        public = EventFactory(is_public=True)
        private = EventFactory(is_public=False)
        cancelled = EventFactory(is_public=True, status=EventStatus.CANCELLED)
        events = get_visible_events(persona=None)
        self.assertIn(public, events)
        self.assertNotIn(private, events)
        self.assertNotIn(cancelled, events)

    def test_persona_sees_public_and_hosted(self) -> None:
        persona = PersonaFactory()
        public = EventFactory(is_public=True)
        private_hosted = EventFactory(is_public=False)
        EventHostFactory(event=private_hosted, persona=persona)
        private_other = EventFactory(is_public=False)
        events = get_visible_events(persona=persona)
        self.assertIn(public, events)
        self.assertIn(private_hosted, events)
        self.assertNotIn(private_other, events)

    def test_persona_sees_invited_events(self) -> None:
        persona = PersonaFactory()
        private_invited = EventFactory(is_public=False)
        EventInvitationFactory(
            event=private_invited,
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
        )
        events = get_visible_events(persona=persona)
        self.assertIn(private_invited, events)

    def test_cancelled_excluded(self) -> None:
        persona = PersonaFactory()
        cancelled = EventFactory(is_public=True, status=EventStatus.CANCELLED)
        events = get_visible_events(persona=persona)
        self.assertNotIn(cancelled, events)
