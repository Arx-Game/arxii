from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.conditions.factories import ensure_radiant_damage_type
from world.locations.constants import KeyType
from world.locations.models import LocationValueOverride


class DamageTypeCascadeDiscriminatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.room_profile = RoomProfileFactory()

    def test_damage_type_override_requires_damage_type_field(self):
        override = LocationValueOverride(
            parent_type="room",
            room_profile=self.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            value=1,
        )
        with self.assertRaises(ValidationError):
            override.full_clean()

    def test_damage_type_override_saves_with_damage_type_set(self):
        override = LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=self.radiant,
            value=1,
        )
        override.refresh_from_db()
        self.assertEqual(override.damage_type_id, self.radiant.pk)
        self.assertEqual(override.stat_key, "")
        self.assertIsNone(override.resonance_id)
