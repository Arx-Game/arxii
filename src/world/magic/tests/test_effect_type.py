"""Tests for the EffectType model."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import BinaryEffectTypeFactory, EffectTypeFactory
from world.magic.models import EffectType


class EffectTypeModelTests(TestCase):
    """Tests for the EffectType model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        # Scaled effect type (Attack with power scaling)
        cls.attack_effect = EffectType.objects.create(
            name="Attack",
            description="Offensive magical effects that deal damage.",
            base_power=10,
            base_anima_cost=2,
            has_power_scaling=True,
        )
        # Binary effect type (Movement without power scaling)
        cls.movement_effect = EffectType.objects.create(
            name="Movement",
            description="Magical effects that enable movement.",
            base_power=None,
            base_anima_cost=1,
            has_power_scaling=False,
        )

    def test_scaled_effect_type_creation(self):
        """Test creation of a scaled effect type with base_power."""
        self.assertEqual(self.attack_effect.name, "Attack")
        self.assertEqual(self.attack_effect.base_power, 10)
        self.assertEqual(self.attack_effect.base_anima_cost, 2)
        self.assertTrue(self.attack_effect.has_power_scaling)

    def test_binary_effect_type_creation(self):
        """Test creation of a binary effect type without power scaling."""
        self.assertEqual(self.movement_effect.name, "Movement")
        self.assertIsNone(self.movement_effect.base_power)
        self.assertEqual(self.movement_effect.base_anima_cost, 1)
        self.assertFalse(self.movement_effect.has_power_scaling)

    def test_effect_type_str(self):
        """Test string representation."""
        self.assertEqual(str(self.attack_effect), "Attack")
        self.assertEqual(str(self.movement_effect), "Movement")

    def test_effect_type_natural_key(self):
        """Test natural_key() returns the name."""
        self.assertEqual(self.attack_effect.natural_key(), ("Attack",))
        self.assertEqual(self.movement_effect.natural_key(), ("Movement",))

    def test_effect_type_get_by_natural_key(self):
        """Test get_by_natural_key() lookup."""
        retrieved = EffectType.objects.get_by_natural_key("Attack")
        self.assertEqual(retrieved, self.attack_effect)

    def test_effect_type_name_unique(self):
        """Test that name is unique."""
        with self.assertRaises(IntegrityError):
            EffectType.objects.create(name="Attack")

    def test_default_base_anima_cost(self):
        """Test that base_anima_cost defaults to 2."""
        effect = EffectType.objects.create(name="Test Effect")
        self.assertEqual(effect.base_anima_cost, 2)

    def test_default_has_power_scaling(self):
        """Test that has_power_scaling defaults to True."""
        effect = EffectType.objects.create(name="Scaling Effect")
        self.assertTrue(effect.has_power_scaling)


class EffectTypeFactoryTests(TestCase):
    """Tests for the EffectTypeFactory."""

    def test_factory_creates_effect_type(self):
        """Test that factory creates a valid EffectType."""
        effect = EffectTypeFactory()
        self.assertIsInstance(effect, EffectType)
        self.assertTrue(effect.name)
        self.assertIsNotNone(effect.base_power)
        self.assertTrue(effect.has_power_scaling)

    def test_factory_get_or_create_on_name(self):
        """Test factory uses get_or_create on name."""
        effect1 = EffectTypeFactory(name="Attack")
        effect2 = EffectTypeFactory(name="Attack")
        self.assertEqual(effect1.pk, effect2.pk)

    def test_binary_factory_creates_binary_effect(self):
        """Test that BinaryEffectTypeFactory creates a binary effect."""
        effect = BinaryEffectTypeFactory()
        self.assertIsInstance(effect, EffectType)
        self.assertIsNone(effect.base_power)
        self.assertFalse(effect.has_power_scaling)

    def test_binary_factory_get_or_create_on_name(self):
        """Test BinaryEffectTypeFactory uses get_or_create on name."""
        effect1 = BinaryEffectTypeFactory(name="Flight")
        effect2 = BinaryEffectTypeFactory(name="Flight")
        self.assertEqual(effect1.pk, effect2.pk)
