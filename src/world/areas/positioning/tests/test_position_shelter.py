"""Tests for PositionShelter and BlueprintPositionShelter models."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

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


class PositionShelterModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")
        cls.room_profile = RoomProfileFactory()
        cls.positions = instantiate_blueprint(cls.blueprint, cls.room_profile.objectdb)
        cls.pos = cls.positions[0]

    def test_position_shelter_stores_value(self):
        """A PositionShelter row stores its value and damage_type."""
        shelter = PositionShelter.objects.create(
            position=self.pos, damage_type=self.radiant, value=100
        )
        shelter.refresh_from_db()
        self.assertEqual(shelter.value, 100)
        self.assertEqual(shelter.damage_type_id, self.radiant.pk)
        self.assertEqual(shelter.change_per_day, 0)
        self.assertEqual(shelter.source, "")

    def test_current_value_zero_rate_returns_value(self):
        """A zero-rate shelter returns its value unchanged."""
        shelter = PositionShelter.objects.create(
            position=self.pos, damage_type=self.radiant, value=50, change_per_day=0
        )
        self.assertEqual(shelter.current_value(), 50)

    def test_current_value_decays_toward_zero(self):
        """A negative change_per_day decays the value toward zero over time."""
        now = timezone.now()
        shelter = PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=100,
            change_per_day=-10,
            applied_at=now - timedelta(days=3),
        )
        # 100 + (-10 * 3) = 70
        self.assertEqual(shelter.current_value(now=now), 70)

    def test_current_value_clamps_at_zero(self):
        """A decayed shelter that crosses zero returns 0, not negative."""
        now = timezone.now()
        shelter = PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=20,
            change_per_day=-10,
            applied_at=now - timedelta(days=5),
        )
        # 20 + (-10 * 5) = -30, clamped to 0
        self.assertEqual(shelter.current_value(now=now), 0)


class BlueprintPositionShelterModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")

    def test_blueprint_shelter_stores_value(self):
        """A BlueprintPositionShelter row stores its value and damage_type."""
        shelter = BlueprintPositionShelter.objects.create(
            blueprint_position=self.bp_pos, damage_type=self.radiant, value=100
        )
        shelter.refresh_from_db()
        self.assertEqual(shelter.value, 100)
        self.assertEqual(shelter.damage_type_id, self.radiant.pk)

    def test_unique_constraint_per_blueprint_position_and_damage_type(self):
        """Only one shelter row per (blueprint_position, damage_type)."""
        from django.db import IntegrityError

        BlueprintPositionShelter.objects.create(
            blueprint_position=self.bp_pos, damage_type=self.radiant, value=50
        )
        with self.assertRaises(IntegrityError):
            BlueprintPositionShelter.objects.create(
                blueprint_position=self.bp_pos, damage_type=self.radiant, value=75
            )
