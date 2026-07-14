"""Tests for the military system models."""

from __future__ import annotations

from django.test import TestCase

from world.battles.constants import DEFAULT_MORALE, UnitQuality
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import PropertyFactory
from world.military.models import (
    Army,
    ArmyMembership,
    MilitaryUnit,
    MilitaryUnitCapability,
)
from world.societies.factories import OrganizationFactory


class MilitaryUnitTests(TestCase):
    """Tests for the MilitaryUnit model."""

    def test_creation_defaults(self) -> None:
        """A MilitaryUnit gets default quality, strength, morale."""
        unit = MilitaryUnit.objects.create(name="Test Legion")
        self.assertEqual(unit.quality, UnitQuality.TRAINED)
        self.assertEqual(unit.strength, 100)
        self.assertEqual(unit.morale, DEFAULT_MORALE)
        self.assertIsNone(unit.individual_count)
        self.assertIsNone(unit.owner_org)
        self.assertIsNone(unit.commander)
        self.assertIsNone(unit.summoned_by)
        self.assertEqual(unit.descriptor, "")

    def test_str(self) -> None:
        """__str__ returns the name."""
        unit = MilitaryUnit.objects.create(name="Red Legion")
        self.assertEqual(str(unit), "Red Legion")

    def test_owner_org_link(self) -> None:
        """A MilitaryUnit can be owned by an Organization."""
        org = OrganizationFactory()
        unit = MilitaryUnit.objects.create(name="House Guard", owner_org=org)
        self.assertEqual(unit.owner_org, org)
        self.assertIn(unit, org.military_units.all())

    def test_effective_capability_absent(self) -> None:
        """effective_capability returns 0 for a capability the unit doesn't have."""
        unit = MilitaryUnit.objects.create(name="Test")
        cap = CapabilityTypeFactory()
        self.assertEqual(unit.effective_capability(cap), 0)

    def test_effective_capability_present(self) -> None:
        """effective_capability returns the magnitude for a capability the unit has."""
        unit = MilitaryUnit.objects.create(name="Test")
        cap = CapabilityTypeFactory()
        MilitaryUnitCapability.objects.create(unit=unit, capability=cap, value=5)
        self.assertEqual(unit.effective_capability(cap), 5)

    def test_has_property_false(self) -> None:
        """has_property returns False when the unit lacks the property."""
        unit = MilitaryUnit.objects.create(name="Test")
        prop = PropertyFactory()
        self.assertFalse(unit.has_property(prop))

    def test_has_property_true(self) -> None:
        """has_property returns True when the unit has the property."""
        unit = MilitaryUnit.objects.create(name="Test")
        prop = PropertyFactory()
        unit.properties.add(prop)
        self.assertTrue(unit.has_property(prop))

    def test_properties_m2m(self) -> None:
        """Properties can be added and queried."""
        unit = MilitaryUnit.objects.create(name="Test")
        prop1 = PropertyFactory()
        prop2 = PropertyFactory()
        unit.properties.set([prop1, prop2])
        self.assertEqual(unit.properties.count(), 2)


class ArmyTests(TestCase):
    """Tests for the Army and ArmyMembership models."""

    def test_creation_defaults(self) -> None:
        """An Army gets a name and is active by default."""
        army = Army.objects.create(name="Grand Army")
        self.assertEqual(army.name, "Grand Army")
        self.assertTrue(army.is_active)
        self.assertIsNone(army.disbanded_at)
        self.assertIsNone(army.commander)
        self.assertIsNone(army.covenant)
        self.assertIsNone(army.campaign_story)

    def test_str(self) -> None:
        """__str__ returns the name."""
        army = Army.objects.create(name="Northern Host")
        self.assertEqual(str(army), "Northern Host")

    def test_add_unit_to_army(self) -> None:
        """A MilitaryUnit can join an Army via ArmyMembership."""
        army = Army.objects.create(name="Test Army")
        unit = MilitaryUnit.objects.create(name="Test Unit")
        membership = ArmyMembership.objects.create(army=army, military_unit=unit)
        self.assertIsNone(membership.left_at)
        self.assertIn(unit, army.active_units)

    def test_unit_leaves_army(self) -> None:
        """A unit can leave an army by setting left_at."""
        army = Army.objects.create(name="Test Army")
        unit = MilitaryUnit.objects.create(name="Test Unit")
        ArmyMembership.objects.create(army=army, military_unit=unit)
        self.assertIn(unit, army.active_units)
        # Now leave
        membership = ArmyMembership.objects.get(army=army, military_unit=unit)
        from django.utils import timezone

        membership.left_at = timezone.now()
        membership.save()
        self.assertNotIn(unit, army.active_units)

    def test_unit_in_multiple_armies(self) -> None:
        """A unit can be in multiple armies simultaneously."""
        army1 = Army.objects.create(name="Army 1")
        army2 = Army.objects.create(name="Army 2")
        unit = MilitaryUnit.objects.create(name="Shared Unit")
        ArmyMembership.objects.create(army=army1, military_unit=unit)
        ArmyMembership.objects.create(army=army2, military_unit=unit)
        self.assertIn(unit, army1.active_units)
        self.assertIn(unit, army2.active_units)

    def test_unique_active_membership(self) -> None:
        """A unit can't have two active memberships in the same army."""
        from django.db import IntegrityError

        army = Army.objects.create(name="Test Army")
        unit = MilitaryUnit.objects.create(name="Test Unit")
        ArmyMembership.objects.create(army=army, military_unit=unit)
        with self.assertRaises(IntegrityError):
            ArmyMembership.objects.create(army=army, military_unit=unit)

    def test_disbanded_army_not_active(self) -> None:
        """An army with disbanded_at set is not active."""
        from django.utils import timezone

        army = Army.objects.create(name="Disbanded Army", disbanded_at=timezone.now())
        self.assertFalse(army.is_active)
