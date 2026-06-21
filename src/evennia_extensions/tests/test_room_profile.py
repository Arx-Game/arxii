from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory


class RoomProfileIsOutdoorTests(TestCase):
    def test_default_is_indoor(self) -> None:
        profile = RoomProfileFactory()
        self.assertFalse(profile.is_outdoor)

    def test_field_is_settable(self) -> None:
        # RoomProfileFactory uses django_get_or_create because Room
        # auto-creates a RoomProfile on save, so kwargs aren't applied to
        # the returned instance. Set and persist the field explicitly.
        profile = RoomProfileFactory()
        profile.is_outdoor = True
        profile.save()
        profile.refresh_from_db()
        self.assertTrue(profile.is_outdoor)


class RoomProfileFactoryAppliesKwargsTests(TestCase):
    """Regression test for Task 6 factory fix.

    Previously, RoomProfileFactory(area=...) silently dropped the kwarg
    because django_get_or_create returned the auto-created row. The
    _create override should apply non-lookup kwargs to the returned
    instance.
    """

    def test_area_kwarg_is_applied(self) -> None:
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory

        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        profile.refresh_from_db()
        self.assertEqual(profile.area, ward)

    def test_is_outdoor_kwarg_is_applied(self) -> None:
        profile = RoomProfileFactory(is_outdoor=True)
        profile.refresh_from_db()
        self.assertTrue(profile.is_outdoor)


class RoomProfileDefaultBlueprintTests(TestCase):
    """Tests for RoomProfile.default_blueprint FK (Task 3 / #1017)."""

    def test_room_profile_default_blueprint_set_null(self) -> None:
        from world.areas.positioning.models import PositionBlueprint

        bp = PositionBlueprint.objects.create(name="Default Hall")
        rp = RoomProfileFactory(default_blueprint=bp)
        bp.delete()
        # SharedMemoryModel idmapper holds the old instance in memory;
        # flush_from_cache() evicts it so refresh_from_db() re-reads from the DB.
        rp.flush_from_cache()
        rp.refresh_from_db()
        self.assertIsNone(rp.default_blueprint_id)


class TestRoomIsPubliclyListed(TestCase):
    def _room(self):
        return ObjectDBFactory(
            db_key="Helper Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_public_profile_returns_true(self) -> None:
        from evennia_extensions.models import room_is_publicly_listed

        room = self._room()  # at_object_creation auto-creates profile, is_public defaults True
        self.assertTrue(room_is_publicly_listed(room))

    def test_non_public_profile_returns_false(self) -> None:
        from evennia_extensions.models import room_is_publicly_listed

        room = self._room()
        room.room_profile.is_public = False
        room.room_profile.save()
        self.assertFalse(room_is_publicly_listed(room))

    def test_missing_profile_returns_false(self) -> None:
        from evennia_extensions.models import room_is_publicly_listed

        room = self._room()
        room.room_profile.delete()
        room.refresh_from_db()
        self.assertFalse(room_is_publicly_listed(room))
