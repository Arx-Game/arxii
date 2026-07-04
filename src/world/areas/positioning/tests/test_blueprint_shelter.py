"""Tests for BlueprintPositionShelter cloning during instantiate_blueprint."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.positioning.models import (
    BlueprintPositionShelter,
    PositionShelter,
)
from world.areas.positioning.services import (
    add_blueprint_position,
    create_blueprint,
    instantiate_blueprint,
)
from world.conditions.factories import ensure_radiant_damage_type


class InstantiateBlueprintShelterCloneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")
        BlueprintPositionShelter.objects.create(
            blueprint_position=cls.bp_pos,
            damage_type=cls.radiant,
            value=100,
        )

    def test_instantiate_clones_shelter_rows(self):
        """instantiate_blueprint creates PositionShelter rows from template."""
        room_profile = RoomProfileFactory()
        positions = instantiate_blueprint(self.blueprint, room_profile.objectdb)
        pos = positions[0]

        shelter = PositionShelter.objects.get(position=pos, damage_type=self.radiant)
        self.assertEqual(shelter.value, 100)
        self.assertEqual(shelter.change_per_day, 0)
        self.assertEqual(shelter.source, "")

    def test_instantiate_no_shelter_template_creates_no_rows(self):
        """A blueprint position with no shelter template creates no PositionShelter."""
        bp = create_blueprint("Empty Room")
        add_blueprint_position(bp, "Center")

        room_profile = RoomProfileFactory()
        positions = instantiate_blueprint(bp, room_profile.objectdb)
        pos = positions[0]

        self.assertFalse(PositionShelter.objects.filter(position=pos).exists())

    def test_instantiate_multiple_shelter_damage_types(self):
        """Multiple damage types on one blueprint position all get cloned."""
        from world.conditions.models import DamageType

        fire = DamageType.objects.create(name="Fire")
        BlueprintPositionShelter.objects.create(
            blueprint_position=self.bp_pos,
            damage_type=fire,
            value=50,
        )

        room_profile = RoomProfileFactory()
        positions = instantiate_blueprint(self.blueprint, room_profile.objectdb)
        pos = positions[0]

        self.assertEqual(PositionShelter.objects.filter(position=pos).count(), 2)
        radiant_shelter = PositionShelter.objects.get(position=pos, damage_type=self.radiant)
        fire_shelter = PositionShelter.objects.get(position=pos, damage_type=fire)
        self.assertEqual(radiant_shelter.value, 100)
        self.assertEqual(fire_shelter.value, 50)

    def test_restage_replaces_shelter_rows(self):
        """replace=True deletes old PositionShelter rows (via cascade-delete on Position)."""
        room_profile = RoomProfileFactory()
        positions = instantiate_blueprint(self.blueprint, room_profile.objectdb)
        pos = positions[0]
        self.assertEqual(PositionShelter.objects.filter(position=pos).count(), 1)

        # Restage with replace=True
        instantiate_blueprint(self.blueprint, room_profile.objectdb, replace=True)
        # Old position was deleted (cascade), new one created with fresh shelter
        self.assertEqual(PositionShelter.objects.filter(damage_type=self.radiant).count(), 1)
