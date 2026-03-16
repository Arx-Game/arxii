"""Tests for Property, Application, and TraitCapabilityDerivation models."""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import (
    ApplicationFactory,
    PropertyCategoryFactory,
    PropertyFactory,
    TraitCapabilityDerivationFactory,
)
from world.mechanics.models import (
    Application,
    Property,
    PropertyCategory,
    TraitCapabilityDerivation,
)
from world.traits.factories import TraitFactory


class PropertyCategoryTests(TestCase):
    """Test PropertyCategory model."""

    def test_str_returns_name(self) -> None:
        """Test __str__ returns name."""
        category = PropertyCategoryFactory(name="Elemental")
        self.assertEqual(str(category), "Elemental")

    def test_unique_name(self) -> None:
        """Test that category names must be unique."""
        PropertyCategoryFactory(name="Physical")
        with self.assertRaises(IntegrityError):
            PropertyCategory.objects.create(name="Physical")


class PropertyTests(TestCase):
    """Test Property model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = PropertyCategoryFactory(name="Elemental")

    def test_str_returns_name(self) -> None:
        """Test __str__ returns name."""
        prop = PropertyFactory(name="Flammable", category=self.category)
        self.assertEqual(str(prop), "Flammable")

    def test_unique_name(self) -> None:
        """Test that property names must be unique."""
        PropertyFactory(name="Locked")
        with self.assertRaises(IntegrityError):
            Property.objects.create(name="Locked", category=self.category)

    def test_category_relationship(self) -> None:
        """Test FK to PropertyCategory works, including reverse relation."""
        prop = PropertyFactory(name="Frozen", category=self.category)
        self.assertEqual(prop.category, self.category)
        self.assertIn(prop, self.category.properties.all())


class ApplicationTests(TestCase):
    """Test Application model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.capability = CapabilityTypeFactory(name="fire_generation")
        cls.target_property = PropertyFactory(name="flammable")

    def test_str_returns_name_with_capability_and_property(self) -> None:
        """Test __str__ returns 'Name (capability + property)'."""
        app = ApplicationFactory(
            name="Ignite",
            capability=self.capability,
            target_property=self.target_property,
        )
        self.assertEqual(str(app), "Ignite (fire_generation + flammable)")

    def test_unique_constraint(self) -> None:
        """Test same capability + property + name raises IntegrityError."""
        ApplicationFactory(
            name="Ignite",
            capability=self.capability,
            target_property=self.target_property,
        )
        with self.assertRaises(IntegrityError):
            Application.objects.create(
                name="Ignite",
                capability=self.capability,
                target_property=self.target_property,
            )

    def test_same_name_different_capability_allowed(self) -> None:
        """Test same name with different capability is allowed."""
        other_capability = CapabilityTypeFactory(name="ice_generation")
        ApplicationFactory(
            name="Blast",
            capability=self.capability,
            target_property=self.target_property,
        )
        app2 = ApplicationFactory(
            name="Blast",
            capability=other_capability,
            target_property=self.target_property,
        )
        self.assertEqual(app2.name, "Blast")

    def test_required_effect_property_nullable(self) -> None:
        """Test required_effect_property defaults to None."""
        app = ApplicationFactory(
            capability=self.capability,
            target_property=self.target_property,
        )
        self.assertIsNone(app.required_effect_property)

    def test_required_effect_property_set(self) -> None:
        """Test required_effect_property can be set."""
        effect_prop = PropertyFactory(name="fire_effect")
        app = ApplicationFactory(
            capability=self.capability,
            target_property=self.target_property,
            required_effect_property=effect_prop,
        )
        self.assertEqual(app.required_effect_property, effect_prop)


class TraitCapabilityDerivationTests(TestCase):
    """Test TraitCapabilityDerivation model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = TraitFactory(name="Strength")
        cls.capability = CapabilityTypeFactory(name="lifting")

    def test_str_contains_arrow(self) -> None:
        """Test __str__ contains arrow between trait and capability."""
        derivation = TraitCapabilityDerivationFactory(
            trait=self.trait,
            capability=self.capability,
        )
        result = str(derivation)
        self.assertIn("→", result)
        self.assertIn("Strength", result)
        self.assertIn("lifting", result)

    def test_calculate_value(self) -> None:
        """Test calculate_value: base_value=5, multiplier=0.3, trait_value=50 → 20."""
        derivation = TraitCapabilityDerivationFactory(
            trait=self.trait,
            capability=self.capability,
            base_value=5,
            trait_multiplier=Decimal("0.3"),
        )
        self.assertEqual(derivation.calculate_value(50), 20)

    def test_calculate_value_zero_multiplier(self) -> None:
        """Test calculate_value: base_value=10, multiplier=0, trait=100 → 10."""
        derivation = TraitCapabilityDerivationFactory(
            trait=self.trait,
            capability=self.capability,
            base_value=10,
            trait_multiplier=Decimal(0),
        )
        self.assertEqual(derivation.calculate_value(100), 10)

    def test_unique_trait_capability(self) -> None:
        """Test same trait + capability raises IntegrityError."""
        TraitCapabilityDerivationFactory(
            trait=self.trait,
            capability=self.capability,
        )
        with self.assertRaises(IntegrityError):
            TraitCapabilityDerivation.objects.create(
                trait=self.trait,
                capability=self.capability,
                base_value=0,
                trait_multiplier=Decimal("1.0"),
            )
