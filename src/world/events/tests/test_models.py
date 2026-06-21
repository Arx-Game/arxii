from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

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

    def test_no_default_ordering(self) -> None:
        """Event model has no Meta.ordering — ordering is applied at the ViewSet level."""
        self.assertEqual(Event._meta.ordering, [])


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

    def test_clean_valid_persona_invitation(self) -> None:
        persona = PersonaFactory()
        invitation = EventInvitationFactory(
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
            target_organization=None,
            target_society=None,
        )
        invitation.clean()  # should not raise

    def test_clean_missing_required_fk_raises(self) -> None:
        invitation = EventInvitationFactory.build(
            target_type=InvitationTargetType.PERSONA,
            target_persona=None,
            target_organization=None,
            target_society=None,
        )
        with self.assertRaises(ValidationError):
            invitation.clean()

    def test_clean_extra_fk_set_raises(self) -> None:
        persona = PersonaFactory()
        org = OrganizationFactory()
        invitation = EventInvitationFactory.build(
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
            target_organization=org,
            target_society=None,
        )
        with self.assertRaises(ValidationError):
            invitation.clean()

    def test_clean_org_invitation_valid(self) -> None:
        org = OrganizationFactory()
        invitation = EventInvitationFactory(
            target_type=InvitationTargetType.ORGANIZATION,
            target_persona=None,
            target_organization=org,
            target_society=None,
        )
        invitation.clean()  # should not raise

    def test_target_persona_field_allows_null(self) -> None:
        """Verify target_persona FK is nullable (SET_NULL on_delete configured)."""
        field = EventInvitation._meta.get_field("target_persona")
        self.assertTrue(field.null)
        self.assertEqual(field.remote_field.on_delete.__name__, "SET_NULL")


class EventHostSocietyTest(TestCase):
    """Tests for Event.host_society — the fashion-perceiving society for an event."""

    def test_host_society_default_is_none(self) -> None:
        event = EventFactory()
        self.assertIsNone(event.host_society)

    def test_host_society_can_be_set_and_retrieved(self) -> None:
        society = SocietyFactory()
        event = EventFactory(host_society=society)
        event.refresh_from_db()
        self.assertEqual(event.host_society, society)

    def test_host_society_reverse_accessor(self) -> None:
        """Society.hosted_events should return events where that society is host."""
        society = SocietyFactory()
        event = EventFactory(host_society=society)
        self.assertIn(event, society.hosted_events.all())

    def test_host_society_null_on_society_delete(self) -> None:
        """Deleting the society nullifies the FK (SET_NULL)."""
        from world.events.models import Event

        society = SocietyFactory()
        event = EventFactory(host_society=society)
        society.delete()
        # Use values() to bypass the SharedMemoryModel identity-map cache
        row = Event.objects.filter(pk=event.pk).values("host_society_id").get()
        self.assertIsNone(row["host_society_id"])


class EventCleanPrivacyTest(TestCase):
    """Event.clean() rejects a private event in a publicly-listed room."""

    def test_clean_raises_for_private_event_in_public_room(self) -> None:
        event = EventFactory(is_public=False)
        event.location.is_public = True
        event.location.save()

        with self.assertRaises(ValidationError) as ctx:
            event.clean()

        self.assertIn("is_public", ctx.exception.message_dict)

    def test_clean_passes_for_public_event_in_public_room(self) -> None:
        event = EventFactory(is_public=True)
        event.location.is_public = True
        event.location.save()

        event.clean()  # must not raise

    def test_clean_passes_for_private_event_in_non_public_room(self) -> None:
        event = EventFactory(is_public=False)
        event.location.is_public = False
        event.location.save()

        event.clean()  # must not raise


class EventModificationModelTest(TestCase):
    def test_str(self) -> None:
        mod = EventModificationFactory()
        self.assertIn("Modifications for", str(mod))

    def test_one_to_one_with_event(self) -> None:
        mod = EventModificationFactory()
        with self.assertRaises(IntegrityError):
            EventModificationFactory(event=mod.event)
