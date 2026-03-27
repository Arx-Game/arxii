from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.events.constants import EventStatus, InvitationTargetType
from world.events.factories import (
    EventFactory,
    EventHostFactory,
    EventInvitationFactory,
    EventModificationFactory,
)
from world.events.models import Event, EventHost, EventInvitation
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, SocietyFactory


class EventModelTest(TestCase):
    def test_str(self) -> None:
        event = EventFactory(name="Grand Ball", status=EventStatus.SCHEDULED)
        self.assertEqual(str(event), "Grand Ball (Scheduled)")

    def test_is_active_when_active(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        self.assertTrue(event.is_active)

    def test_is_active_when_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        self.assertFalse(event.is_active)

    def test_is_upcoming_when_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        self.assertTrue(event.is_upcoming)

    def test_is_upcoming_when_completed(self) -> None:
        event = EventFactory(status=EventStatus.COMPLETED)
        self.assertFalse(event.is_upcoming)

    def test_default_status_is_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        self.assertEqual(event.status, EventStatus.DRAFT)

    def test_ordering_by_scheduled_real_time(self) -> None:
        now = timezone.now()
        event_later = EventFactory(scheduled_real_time=now + timezone.timedelta(hours=12))
        event_sooner = EventFactory(scheduled_real_time=now + timezone.timedelta(hours=1))
        events = list(Event.objects.filter(id__in=[event_later.id, event_sooner.id]))
        self.assertEqual(events[0].id, event_sooner.id)
        self.assertEqual(events[1].id, event_later.id)


class EventHostModelTest(TestCase):
    def test_str(self) -> None:
        host = EventHostFactory()
        self.assertIn("hosting", str(host))
        self.assertIn(host.event.name, str(host))

    def test_unique_event_persona(self) -> None:
        host = EventHostFactory()
        with self.assertRaises(IntegrityError):
            EventHostFactory(event=host.event, persona=host.persona)

    def test_persona_field_allows_null(self) -> None:
        """Verify persona FK is nullable (SET_NULL on_delete configured)."""
        field = EventHost._meta.get_field("persona")
        self.assertTrue(field.null)
        self.assertEqual(field.remote_field.on_delete.__name__, "SET_NULL")


class EventInvitationModelTest(TestCase):
    def test_str_persona_invitation(self) -> None:
        persona = PersonaFactory()
        invitation = EventInvitationFactory(
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
        )
        self.assertIn(persona.name, str(invitation))

    def test_str_organization_invitation(self) -> None:
        org = OrganizationFactory()
        invitation = EventInvitationFactory(
            target_type=InvitationTargetType.ORGANIZATION,
            target_persona=None,
            target_organization=org,
        )
        self.assertIn(org.name, str(invitation))

    def test_str_society_invitation(self) -> None:
        society = SocietyFactory()
        invitation = EventInvitationFactory(
            target_type=InvitationTargetType.SOCIETY,
            target_persona=None,
            target_society=society,
        )
        self.assertIn(society.name, str(invitation))

    def test_unique_persona_invitation_per_event(self) -> None:
        event = EventFactory()
        persona = PersonaFactory()
        EventInvitationFactory(
            event=event,
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
        )
        with self.assertRaises(IntegrityError):
            EventInvitationFactory(
                event=event,
                target_type=InvitationTargetType.PERSONA,
                target_persona=persona,
            )

    def test_target_persona_field_allows_null(self) -> None:
        """Verify target_persona FK is nullable (SET_NULL on_delete configured)."""
        field = EventInvitation._meta.get_field("target_persona")
        self.assertTrue(field.null)
        self.assertEqual(field.remote_field.on_delete.__name__, "SET_NULL")


class EventModificationModelTest(TestCase):
    def test_str(self) -> None:
        mod = EventModificationFactory()
        self.assertIn("Modifications for", str(mod))

    def test_one_to_one_with_event(self) -> None:
        mod = EventModificationFactory()
        with self.assertRaises(IntegrityError):
            EventModificationFactory(event=mod.event)
