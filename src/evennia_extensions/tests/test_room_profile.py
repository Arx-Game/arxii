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
