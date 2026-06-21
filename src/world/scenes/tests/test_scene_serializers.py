"""Serializer-level privacy validation for scene create/update (#1299).

Tests that SceneListSerializer (and SceneDetailSerializer which subclasses it)
rejects a non-public privacy_mode paired with a publicly-listed room location,
returning a 400-friendly ValidationError rather than letting the violation reach
Scene.save() and 500.

Built in setUp: Evennia ObjectDB instances are not deepcopyable so setUpTestData
would break.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.serializers import SceneDetailSerializer


class TestSceneSerializerPrivacyValidation(TestCase):
    """SceneDetailSerializer rejects non-public privacy_mode in a public room."""

    def setUp(self) -> None:
        self.public_room = ObjectDBFactory(
            db_key="Public Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.private_room = ObjectDBFactory(
            db_key="Private Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.private_room.room_profile.is_public = False
        self.private_room.room_profile.save()

    def _serializer(self, room, privacy_mode: str) -> SceneDetailSerializer:
        return SceneDetailSerializer(
            data={
                "name": "Test Scene",
                "location_id": room.pk,
                "privacy_mode": privacy_mode,
            }
        )

    def test_private_in_public_room_is_invalid(self) -> None:
        """PRIVATE scene in a publicly-listed room → invalid, error on privacy_mode."""
        s = self._serializer(self.public_room, ScenePrivacyMode.PRIVATE)
        self.assertFalse(s.is_valid())
        self.assertIn("privacy_mode", s.errors)

    def test_ephemeral_in_public_room_is_invalid(self) -> None:
        """EPHEMERAL scene in a publicly-listed room → invalid, error on privacy_mode."""
        s = self._serializer(self.public_room, ScenePrivacyMode.EPHEMERAL)
        self.assertFalse(s.is_valid())
        self.assertIn("privacy_mode", s.errors)

    def test_public_in_public_room_is_valid(self) -> None:
        """PUBLIC scene in a publicly-listed room → valid."""
        s = self._serializer(self.public_room, ScenePrivacyMode.PUBLIC)
        self.assertTrue(s.is_valid(), s.errors)

    def test_private_in_non_public_room_is_valid(self) -> None:
        """PRIVATE scene in a non-public room → valid."""
        s = self._serializer(self.private_room, ScenePrivacyMode.PRIVATE)
        self.assertTrue(s.is_valid(), s.errors)
