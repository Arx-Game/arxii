"""Identity/origin fields for grid export (#2448)."""

from django.test import TestCase
from evennia.utils import create as evennia_create

from evennia_extensions.models import RoomProfile, RoomSizeTier
from world.areas.constants import GridOrigin


class RoomProfileIdentityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Test Hall", nohome=True
        )

    def test_defaults_are_player_origin_with_no_fixture_key(self):
        profile = self.room.room_profile
        self.assertEqual(profile.origin, GridOrigin.PLAYER)
        self.assertIsNone(profile.fixture_key)

    def test_get_by_natural_key_resolves_fixture_key(self):
        profile = self.room.room_profile
        profile.fixture_key = "arx-city/test-hall"
        profile.origin = GridOrigin.AUTHORED
        profile.save()
        found = RoomProfile.objects.get_by_natural_key("arx-city/test-hall")
        self.assertEqual(found.pk, profile.pk)
        self.assertEqual(profile.natural_key(), ("arx-city/test-hall",))

    def test_room_size_tier_natural_key(self):
        tier = RoomSizeTier.objects.create(name="Vast-Test", units=999)
        self.assertEqual(RoomSizeTier.objects.get_by_natural_key("Vast-Test").pk, tier.pk)
