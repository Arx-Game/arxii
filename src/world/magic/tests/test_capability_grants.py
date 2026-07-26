"""Tests for the TechniqueCapabilityGrant model."""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import TechniqueCapabilityGrantFactory, TechniqueFactory
from world.magic.models import CapabilityPowerConfig, TechniqueCapabilityGrant


class TechniqueCapabilityGrantTests(TestCase):
    """Tests for TechniqueCapabilityGrant model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(name="Fireball", intensity=10)
        cls.capability = CapabilityTypeFactory(name="Fire Control")

    def test_str(self) -> None:
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        result = str(grant)
        assert "grants" in result
        assert "Fireball" in result
        assert "Fire Control" in result

    def test_calculate_value_from_technique(self) -> None:
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.5"),
        )
        # 5 + (1.5 * 10) = 20
        assert grant.calculate_value() == 20

    def test_calculate_value_override(self) -> None:
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.5"),
        )
        # 5 + (1.5 * 20) = 35
        assert grant.calculate_value(effective_power=20) == 35

    def test_calculate_value_zero_multiplier(self) -> None:
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=10,
            intensity_multiplier=Decimal(0),
        )
        # 10 + (0 * 10) = 10
        assert grant.calculate_value() == 10

    def test_unique_technique_capability(self) -> None:
        TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
        )
        with self.assertRaises(IntegrityError):
            TechniqueCapabilityGrant.objects.create(
                technique=self.technique,
                capability=self.capability,
            )

    def test_prerequisite_null_by_default(self) -> None:
        grant = TechniqueCapabilityGrantFactory(
            technique=self.technique,
            capability=self.capability,
        )
        assert grant.prerequisite is None

    def test_prerequisite_set(self) -> None:
        from world.mechanics.factories import PrerequisiteFactory

        prereq = PrerequisiteFactory(name="shadows_present")
        grant = TechniqueCapabilityGrantFactory(
            technique=self.technique,
            capability=self.capability,
            prerequisite=prereq,
        )
        assert grant.prerequisite_id == prereq.id


class CapabilityGrantCurveTests(TestCase):
    """The curve replaces the additive term once a CapabilityPowerConfig row exists (#2708)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(name="Iron Skin", intensity=3)
        cls.capability = CapabilityTypeFactory(name="Armor")

    def test_inert_without_config(self) -> None:
        """THE critical invariant: no config row means today's exact number."""
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        self.assertEqual(grant.calculate_value(), 8)  # 5 + 1.0 * 3, pre-#2708

    def test_zero_sensitivity_rows_unchanged_with_config(self) -> None:
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal(0),
        )
        self.assertEqual(grant.calculate_value(), 5)

    def test_curves_with_explicit_power(self) -> None:
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        grant = TechniqueCapabilityGrant.objects.create(
            technique=self.technique,
            capability=self.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        self.assertEqual(grant.calculate_value(effective_power=10), 10)
        self.assertEqual(grant.calculate_value(effective_power=30), 40)
