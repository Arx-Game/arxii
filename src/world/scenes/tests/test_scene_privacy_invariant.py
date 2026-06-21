"""Scene privacy<->room-publicness invariant (#1287)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import Scene


class TestScenePrivacyInvariant(TestCase):
    def _room(self, *, public: bool):
        room = ObjectDBFactory(
            db_key="Invariant Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        if not public:
            room.room_profile.is_public = False
            room.room_profile.save()
        return room

    def test_private_scene_in_public_room_raises(self) -> None:
        room = self._room(public=True)
        with self.assertRaises(ValidationError):
            Scene.objects.create(name="Leak", location=room, privacy_mode=ScenePrivacyMode.PRIVATE)

    def test_ephemeral_scene_in_public_room_raises(self) -> None:
        room = self._room(public=True)
        with self.assertRaises(ValidationError):
            Scene.objects.create(
                name="Leak", location=room, privacy_mode=ScenePrivacyMode.EPHEMERAL
            )

    def test_public_scene_in_public_room_ok(self) -> None:
        room = self._room(public=True)
        scene = Scene.objects.create(
            name="Fine", location=room, privacy_mode=ScenePrivacyMode.PUBLIC
        )
        self.assertEqual(scene.privacy_mode, ScenePrivacyMode.PUBLIC)

    def test_private_scene_in_non_public_room_ok(self) -> None:
        room = self._room(public=False)
        scene = Scene.objects.create(
            name="Chambers", location=room, privacy_mode=ScenePrivacyMode.PRIVATE
        )
        self.assertEqual(scene.privacy_mode, ScenePrivacyMode.PRIVATE)

    def test_private_scene_without_location_ok(self) -> None:
        scene = Scene.objects.create(name="Floating", privacy_mode=ScenePrivacyMode.PRIVATE)
        self.assertIsNone(scene.location_id)

    def test_clean_also_raises(self) -> None:
        room = self._room(public=True)
        scene = Scene(name="Leak", location=room, privacy_mode=ScenePrivacyMode.PRIVATE)
        with self.assertRaises(ValidationError):
            scene.clean()
