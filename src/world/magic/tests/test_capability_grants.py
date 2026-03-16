"""Tests for the TechniqueCapabilityGrant model."""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import TechniqueCapabilityGrantFactory, TechniqueFactory
from world.magic.models import TechniqueCapabilityGrant


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
        assert grant.calculate_value(intensity=20) == 35

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

    def test_prerequisite_key_blank(self) -> None:
        grant = TechniqueCapabilityGrantFactory(
            technique=self.technique,
            capability=self.capability,
        )
        assert grant.prerequisite_key == ""

    def test_prerequisite_key_set(self) -> None:
        grant = TechniqueCapabilityGrantFactory(
            technique=self.technique,
            capability=self.capability,
            prerequisite_key="shadows_present",
        )
        assert grant.prerequisite_key == "shadows_present"
