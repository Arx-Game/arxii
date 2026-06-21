"""Tests for event serializers — focus on config-time privacy validation."""

from django.test import TestCase
from django.utils import timezone

from world.events.factories import EventFactory
from world.events.serializers import EventCreateSerializer, EventUpdateSerializer


def _future_dt(days: int = 1) -> str:
    dt = timezone.now() + timezone.timedelta(days=days)
    return dt.isoformat()


class EventCreateSerializerPrivacyTest(TestCase):
    """EventCreateSerializer rejects a private event in a publicly-listed room."""

    def _base_payload(self, location_id: int) -> dict:
        return {
            "name": "Test Event",
            "description": "A description.",
            "location": location_id,
            "is_public": True,
            "scheduled_real_time": _future_dt(1),
            "scheduled_ic_time": _future_dt(3),
        }

    def test_invalid_when_private_event_in_public_room(self) -> None:
        """A private event whose location is publicly listed must fail validation."""
        event = EventFactory()
        event.location.is_public = True
        event.location.save()

        payload = self._base_payload(event.location.pk)
        payload["is_public"] = False

        serializer = EventCreateSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("is_public", serializer.errors)

    def test_valid_when_public_event_in_public_room(self) -> None:
        """A public event in a publicly-listed room is fine."""
        event = EventFactory()
        event.location.is_public = True
        event.location.save()

        payload = self._base_payload(event.location.pk)
        payload["is_public"] = True

        serializer = EventCreateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_when_private_event_in_non_public_room(self) -> None:
        """A private event in a non-public room is fine."""
        event = EventFactory()
        event.location.is_public = False
        event.location.save()

        payload = self._base_payload(event.location.pk)
        payload["is_public"] = False

        serializer = EventCreateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class EventUpdateSerializerPrivacyTest(TestCase):
    """EventUpdateSerializer rejects flipping is_public=False when room is public."""

    def test_invalid_when_flipping_to_private_in_public_room(self) -> None:
        """Updating is_public=False on an event in a public room must fail."""
        event = EventFactory(is_public=True)
        event.location.is_public = True
        event.location.save()

        serializer = EventUpdateSerializer(
            instance=event,
            data={"is_public": False},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("is_public", serializer.errors)

    def test_valid_when_keeping_public_in_public_room(self) -> None:
        """Updating is_public=True on a public room event is fine."""
        event = EventFactory(is_public=True)
        event.location.is_public = True
        event.location.save()

        serializer = EventUpdateSerializer(
            instance=event,
            data={"is_public": True},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_when_flipping_to_private_in_non_public_room(self) -> None:
        """Updating is_public=False on an event in a non-public room is fine."""
        event = EventFactory(is_public=True)
        event.location.is_public = False
        event.location.save()

        serializer = EventUpdateSerializer(
            instance=event,
            data={"is_public": False},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
