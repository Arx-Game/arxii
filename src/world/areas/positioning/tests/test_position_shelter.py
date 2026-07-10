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
    cleanup_position_shelters,
    create_blueprint,
    instantiate_blueprint,
    position_shelter_value,
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


class PositionShelterValueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")
        cls.room_profile = RoomProfileFactory()
        cls.positions = instantiate_blueprint(cls.blueprint, cls.room_profile.objectdb)
        cls.pos = cls.positions[0]

    def test_no_shelter_rows_returns_zero(self):
        """A position with no shelter rows returns 0."""
        self.assertEqual(position_shelter_value(self.pos, self.radiant), 0)

    def test_single_shelter_row(self):
        """A single shelter row returns its value."""
        PositionShelter.objects.create(position=self.pos, damage_type=self.radiant, value=100)
        self.assertEqual(position_shelter_value(self.pos, self.radiant), 100)

    def test_multiple_shelter_rows_stack(self):
        """Multiple shelter rows on the same position sum additively."""
        PositionShelter.objects.create(position=self.pos, damage_type=self.radiant, value=30)
        PositionShelter.objects.create(
            position=self.pos, damage_type=self.radiant, value=70, source="ward"
        )
        self.assertEqual(position_shelter_value(self.pos, self.radiant), 100)


class CleanupPositionSheltersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.radiant = ensure_radiant_damage_type()
        cls.blueprint = create_blueprint("Tavern")
        cls.bp_pos = add_blueprint_position(cls.blueprint, "Under the Table")
        cls.room_profile = RoomProfileFactory()
        cls.positions = instantiate_blueprint(cls.blueprint, cls.room_profile.objectdb)
        cls.pos = cls.positions[0]

    def test_static_shelter_not_deleted(self):
        """A zero-rate shelter is never deleted."""
        PositionShelter.objects.create(
            position=self.pos, damage_type=self.radiant, value=100, change_per_day=0
        )
        deleted = cleanup_position_shelters()
        self.assertEqual(deleted, 0)
        self.assertEqual(PositionShelter.objects.count(), 1)

    def test_decayed_shelter_deleted(self):
        """A shelter that has decayed to zero is deleted."""
        now = timezone.now()
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=10,
            change_per_day=-10,
            applied_at=now - timedelta(days=5),
        )
        deleted = cleanup_position_shelters(now=now)
        self.assertEqual(deleted, 1)
        self.assertEqual(PositionShelter.objects.count(), 0)


class PositionShelterAttacksOnlyTests(TestCase):
    """Tests for the applies_to_attacks flag and attacks_only filter."""

    def setUp(self):
        from evennia import create_object

        from world.areas.positioning.services import create_position

        self.room = create_object("typeclasses.rooms.Room", key="ShelterAtkRoom", nohome=True)
        self.pos = create_position(self.room, "shelter_atk_pos")
        self.radiant = ensure_radiant_damage_type()

    def test_attack_shelter_included_by_default(self):
        """position_shelter_value returns attack-cover when attacks_only=False."""
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=20,
            applies_to_attacks=True,
        )
        self.assertEqual(position_shelter_value(self.pos, self.radiant), 20)

    def test_attacks_only_returns_attack_cover(self):
        """position_shelter_value(attacks_only=True) returns only attack-cover rows."""
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=20,
            applies_to_attacks=True,
        )
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=50,
            applies_to_attacks=False,
        )
        self.assertEqual(position_shelter_value(self.pos, self.radiant, attacks_only=True), 20)
        self.assertEqual(position_shelter_value(self.pos, self.radiant), 70)

    def test_no_attack_shelter_returns_zero(self):
        """position_shelter_value(attacks_only=True) returns 0 when no attack-cover rows."""
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=50,
            applies_to_attacks=False,
        )
        self.assertEqual(position_shelter_value(self.pos, self.radiant, attacks_only=True), 0)

    def test_default_applies_to_attacks_is_false(self):
        """New PositionShelter rows default applies_to_attacks=False (hazard-only)."""
        shelter = PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.radiant,
            value=10,
        )
        self.assertFalse(shelter.applies_to_attacks)
