"""Tests for RoomsByPropertyView (GET /api/magic/rooms-by-property/).

Covers:
- Rooms tagged with various properties are filtered correctly by property_id.
- Multiple property_id params return rooms bearing ANY of those properties.
- GET with no property_id returns 400.
- GET with non-integer property_id returns 400.
- Auth required (unauthenticated → 401/403).
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.mechanics.factories import ObjectPropertyFactory, PropertyFactory

_URL = "/api/magic/rooms-by-property/"


def _make_room(key: str) -> ObjectDB:  # type: ignore[name-defined]
    """Create an ObjectDB with a room typeclass path."""

    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class RoomsByPropertyFilterTests(APITestCase):
    """Core filtering — only rooms bearing the requested properties are returned."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rooms_prop_account")

        cls.prop_a = PropertyFactory(name="RoomsPropA")
        cls.prop_b = PropertyFactory(name="RoomsPropB")
        cls.prop_c = PropertyFactory(name="RoomsPropC")

        # r1 has prop_a only
        cls.r1 = _make_room("RoomsPropRoom1")
        ObjectPropertyFactory(object=cls.r1, property=cls.prop_a)

        # r2 has prop_a and prop_b
        cls.r2 = _make_room("RoomsPropRoom2")
        ObjectPropertyFactory(object=cls.r2, property=cls.prop_a)
        ObjectPropertyFactory(object=cls.r2, property=cls.prop_b)

        # r3 has prop_c only
        cls.r3 = _make_room("RoomsPropRoom3")
        ObjectPropertyFactory(object=cls.r3, property=cls.prop_c)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_single_property_returns_matching_rooms(self) -> None:
        """GET ?property_id=A returns only r1 and r2 (both bear prop_a)."""
        response = self.client.get(_URL, {"property_id": self.prop_a.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(self.r1.pk, ids)
        self.assertIn(self.r2.pk, ids)
        self.assertNotIn(self.r3.pk, ids)

    def test_multiple_property_ids_return_union(self) -> None:
        """GET ?property_id=A&property_id=C returns r1, r2, and r3."""
        response = self.client.get(_URL, {"property_id": [self.prop_a.pk, self.prop_c.pk]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(self.r1.pk, ids)
        self.assertIn(self.r2.pk, ids)
        self.assertIn(self.r3.pk, ids)

    def test_no_duplicate_rooms_when_room_has_multiple_matching_properties(self) -> None:
        """r2 matches both prop_a and prop_b; it must appear only once."""
        response = self.client.get(_URL, {"property_id": [self.prop_a.pk, self.prop_b.pk]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        r2_count = sum(1 for item in response.data if item["id"] == self.r2.pk)
        self.assertEqual(r2_count, 1)


class RoomsByPropertyValidationTests(APITestCase):
    """Input validation — missing or non-integer property_id returns 400."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rooms_prop_validation_account")

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_missing_property_id_returns_400(self) -> None:
        """GET with no property_id param should return 400."""
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_integer_property_id_returns_400(self) -> None:
        """GET ?property_id=notanumber should return 400."""
        response = self.client.get(_URL, {"property_id": "notanumber"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RoomsByPropertyAuthTests(APITestCase):
    """Auth required — unauthenticated request is rejected."""

    def test_unauthenticated_returns_401(self) -> None:
        """Unauthenticated GET should be rejected."""
        response = self.client.get(_URL, {"property_id": 1})
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )
