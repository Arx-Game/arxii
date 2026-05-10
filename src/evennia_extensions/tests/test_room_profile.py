from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory


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
