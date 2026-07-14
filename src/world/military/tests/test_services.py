"""Tests for the military system services."""

from __future__ import annotations

from django.test import TestCase

from world.military.factories import ArmyFactory, MilitaryUnitFactory
from world.military.models import ArmyMembership, MilitaryUnit
from world.military.services import (
    add_unit_to_army,
    create_military_unit,
    disband_army,
    form_army,
    remove_unit_from_army,
)
from world.societies.factories import OrganizationFactory


class CreateMilitaryUnitTests(TestCase):
    """Tests for create_military_unit service."""

    def test_creates_unit_with_defaults(self) -> None:
        """create_military_unit creates a MilitaryUnit with default values."""
        unit = create_military_unit(name="Test Legion")
        self.assertEqual(unit.name, "Test Legion")
        self.assertEqual(unit.strength, 100)
        self.assertEqual(unit.quality, "trained")
        self.assertIsNone(unit.owner_org)

    def test_creates_unit_with_owner_org(self) -> None:
        """create_military_unit links the owner_org."""
        org = OrganizationFactory()
        unit = create_military_unit(name="House Guard", owner_org=org)
        self.assertEqual(unit.owner_org, org)


class FormArmyTests(TestCase):
    """Tests for form_army service."""

    def test_creates_army_with_no_units(self) -> None:
        """form_army creates an Army with no initial units."""
        army = form_army(name="Grand Army")
        self.assertEqual(army.name, "Grand Army")
        self.assertTrue(army.is_active)
        self.assertEqual(army.active_units.count(), 0)

    def test_creates_army_with_units(self) -> None:
        """form_army creates an Army with initial units."""
        unit1 = MilitaryUnitFactory()
        unit2 = MilitaryUnitFactory()
        army = form_army(name="Grand Army", units=[unit1, unit2])
        self.assertEqual(army.active_units.count(), 2)
        self.assertIn(unit1, army.active_units)
        self.assertIn(unit2, army.active_units)


class DisbandArmyTests(TestCase):
    """Tests for disband_army service."""

    def test_disbands_army(self) -> None:
        """disband_army sets disbanded_at and leaves all memberships."""
        unit1 = MilitaryUnitFactory()
        unit2 = MilitaryUnitFactory()
        army = form_army(name="Grand Army", units=[unit1, unit2])
        self.assertTrue(army.is_active)
        self.assertEqual(army.active_units.count(), 2)

        disband_army(army=army)
        army.refresh_from_db()
        self.assertFalse(army.is_active)
        self.assertEqual(army.active_units.count(), 0)
        # Units still exist — they persist after army disbands
        MilitaryUnit.objects.get(pk=unit1.pk)
        MilitaryUnit.objects.get(pk=unit2.pk)


class ArmyMembershipTests(TestCase):
    """Tests for add_unit_to_army and remove_unit_from_army services."""

    def test_add_unit_to_army(self) -> None:
        """add_unit_to_army creates an active membership."""
        army = ArmyFactory()
        unit = MilitaryUnitFactory()
        membership = add_unit_to_army(army=army, military_unit=unit)
        self.assertIsNone(membership.left_at)
        self.assertIn(unit, army.active_units)

    def test_add_unit_idempotent(self) -> None:
        """Adding a unit already in the army is idempotent."""
        army = ArmyFactory()
        unit = MilitaryUnitFactory()
        m1 = add_unit_to_army(army=army, military_unit=unit)
        m2 = add_unit_to_army(army=army, military_unit=unit)
        self.assertEqual(m1.pk, m2.pk)

    def test_remove_unit_from_army(self) -> None:
        """remove_unit_from_army sets left_at on the membership."""
        army = ArmyFactory()
        unit = MilitaryUnitFactory()
        add_unit_to_army(army=army, military_unit=unit)
        self.assertIn(unit, army.active_units)
        remove_unit_from_army(army=army, military_unit=unit)
        self.assertNotIn(unit, army.active_units)

    def test_unit_in_multiple_armies(self) -> None:
        """A unit can be added to multiple armies."""
        army1 = ArmyFactory()
        army2 = ArmyFactory()
        unit = MilitaryUnitFactory()
        add_unit_to_army(army=army1, military_unit=unit)
        add_unit_to_army(army=army2, military_unit=unit)
        self.assertIn(unit, army1.active_units)
        self.assertIn(unit, army2.active_units)

    def test_removed_unit_can_rejoin(self) -> None:
        """A unit that left can rejoin (new active membership)."""
        army = ArmyFactory()
        unit = MilitaryUnitFactory()
        add_unit_to_army(army=army, military_unit=unit)
        remove_unit_from_army(army=army, military_unit=unit)
        add_unit_to_army(army=army, military_unit=unit)
        self.assertIn(unit, army.active_units)
        # Old membership has left_at set, new one doesn't
        self.assertEqual(
            ArmyMembership.objects.filter(army=army, military_unit=unit).count(),
            2,
        )
