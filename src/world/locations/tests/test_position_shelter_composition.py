"""Tests for hazard_is_covered_for — room cascade + position shelter composition."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.positioning.models import PositionShelter
from world.areas.positioning.services import (
    add_blueprint_position,
    create_blueprint,
    instantiate_blueprint,
    place_in_position,
)
from world.conditions.factories import ensure_radiant_damage_type
from world.locations.constants import KeyType
from world.locations.models import LocationValueModifier, LocationValueOverride
from world.locations.services import hazard_is_covered_for


class HazardIsCoveredForTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.room_profile = RoomProfileFactory()
        cls.room = cls.room_profile.objectdb
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")
        cls.positions = instantiate_blueprint(cls.blueprint, cls.room)
        cls.shelter_pos = cls.positions[0]

    def _create_character(self):
        from evennia import create_object

        return create_object(
            "typeclasses.characters.Character",
            key="TestChar",
            location=self.room,
            nohome=True,
        )

    def test_no_position_no_room_shelter_returns_false(self):
        """A character with no position in an unsheltered room is not covered."""
        char = self._create_character()
        self.assertFalse(hazard_is_covered_for(char, self.room, self.radiant))

    def test_position_shelter_covers_character(self):
        """A character at a sheltering position is covered even in an unsheltered room."""
        char = self._create_character()
        place_in_position(char, self.shelter_pos)
        PositionShelter.objects.create(
            position=self.shelter_pos, damage_type=self.radiant, value=100
        )
        self.assertTrue(hazard_is_covered_for(char, self.room, self.radiant))

    def test_no_position_in_sheltered_room_returns_true(self):
        """A character with no position in a room-level-sheltered room is covered."""
        LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=self.radiant,
            value=1,
        )
        char = self._create_character()
        self.assertTrue(hazard_is_covered_for(char, self.room, self.radiant))

    def test_position_shelter_adds_to_room_shelter(self):
        """Room shelter + position shelter stack additively."""
        LocationValueModifier.objects.create(
            parent_type="room",
            room_profile=self.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=self.radiant,
            value=50,
        )
        PositionShelter.objects.create(
            position=self.shelter_pos, damage_type=self.radiant, value=100
        )
        char = self._create_character()
        place_in_position(char, self.shelter_pos)
        # Total = 50 (room) + 100 (position) = 150
        self.assertTrue(hazard_is_covered_for(char, self.room, self.radiant, threshold=150))

    def test_position_shelter_overrides_room_no_shelter(self):
        """A tent shelters even when the room has an override saying no shelter."""
        LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=self.radiant,
            value=0,
        )
        # Position (tent) has shelter
        PositionShelter.objects.create(
            position=self.shelter_pos, damage_type=self.radiant, value=100
        )
        char = self._create_character()
        place_in_position(char, self.shelter_pos)
        self.assertTrue(hazard_is_covered_for(char, self.room, self.radiant))

    def test_room_none_returns_false(self):
        """room=None is not covered (no cascade, no position)."""
        char = self._create_character()
        self.assertFalse(hazard_is_covered_for(char, None, self.radiant))
