"""Tests for the Restriction model."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import EffectTypeFactory, RestrictionFactory
from world.magic.models import EffectType, Restriction


class RestrictionModelTests(TestCase):
    """Tests for the Restriction model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.attack_effect = EffectType.objects.create(
            name="Attack",
            description="Offensive magical effects.",
            base_power=10,
        )
        cls.defense_effect = EffectType.objects.create(
            name="Defense",
            description="Defensive magical effects.",
            base_power=10,
        )
        cls.restriction = Restriction.objects.create(
            name="Touch Range",
            description="Requires physical contact with the target.",
            power_bonus=10,
        )
        cls.restriction.allowed_effect_types.add(cls.attack_effect, cls.defense_effect)

    def test_restriction_creation(self):
        """Test creation of a restriction with allowed effect types."""
        self.assertEqual(self.restriction.name, "Touch Range")
        self.assertEqual(self.restriction.description, "Requires physical contact with the target.")
        self.assertEqual(self.restriction.power_bonus, 10)

    def test_restriction_str_shows_power_bonus(self):
        """Test string representation shows power bonus."""
        self.assertEqual(str(self.restriction), "Touch Range (+10)")

    def test_restriction_natural_key(self):
        """Test natural_key() returns the name."""
        self.assertEqual(self.restriction.natural_key(), ("Touch Range",))

    def test_restriction_get_by_natural_key(self):
        """Test get_by_natural_key() lookup."""
        retrieved = Restriction.objects.get_by_natural_key("Touch Range")
        self.assertEqual(retrieved, self.restriction)

    def test_restriction_allowed_effect_types(self):
        """Test that restriction can have allowed effect types."""
        self.assertEqual(self.restriction.allowed_effect_types.count(), 2)
        self.assertIn(self.attack_effect, self.restriction.allowed_effect_types.all())
        self.assertIn(self.defense_effect, self.restriction.allowed_effect_types.all())

    def test_restriction_name_unique(self):
        """Test that name is unique."""
        with self.assertRaises(IntegrityError):
            Restriction.objects.create(name="Touch Range")

    def test_effect_type_has_available_restrictions_reverse_relation(self):
        """Test that EffectType has reverse relation to available restrictions."""
        self.assertIn(self.restriction, self.attack_effect.available_restrictions.all())

    def test_default_power_bonus(self):
        """Test that power_bonus defaults to 10."""
        restriction = Restriction.objects.create(name="Default Bonus")
        self.assertEqual(restriction.power_bonus, 10)


class RestrictionFactoryTests(TestCase):
    """Tests for the RestrictionFactory."""

    def test_factory_creates_restriction(self):
        """Test that factory creates a valid Restriction."""
        restriction = RestrictionFactory()
        self.assertIsInstance(restriction, Restriction)
        self.assertTrue(restriction.name)

    def test_factory_with_allowed_effect_types(self):
        """Test factory can add allowed effect types via post_generation."""
        effect1 = EffectTypeFactory(name="Test Effect 1")
        effect2 = EffectTypeFactory(name="Test Effect 2")
        restriction = RestrictionFactory(allowed_effect_types=[effect1, effect2])
        self.assertEqual(restriction.allowed_effect_types.count(), 2)
        self.assertIn(effect1, restriction.allowed_effect_types.all())
        self.assertIn(effect2, restriction.allowed_effect_types.all())

    def test_factory_get_or_create_on_name(self):
        """Test factory uses get_or_create on name."""
        restriction1 = RestrictionFactory(name="Undead Only")
        restriction2 = RestrictionFactory(name="Undead Only")
        self.assertEqual(restriction1.pk, restriction2.pk)
