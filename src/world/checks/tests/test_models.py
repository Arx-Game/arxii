"""Tests for check system models."""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
from world.traits.models import Trait, TraitCategory, TraitType


class CheckCategoryTests(TestCase):
    """Test CheckCategory model."""

    def test_str_returns_name(self):
        category = CheckCategoryFactory(name="Social")
        assert str(category) == "Social"

    def test_unique_name(self):
        CheckCategoryFactory(name="Social")
        with self.assertRaises(IntegrityError):
            CheckCategory.objects.create(name="Social", display_order=99)


class CheckTypeTests(TestCase):
    """Test CheckType model."""

    def test_str_returns_name(self):
        check_type = CheckTypeFactory(name="Diplomacy")
        assert str(check_type) == "Diplomacy"

    def test_unique_name_within_category(self):
        category = CheckCategoryFactory(name="Social")
        CheckTypeFactory(name="Diplomacy", category=category)
        with self.assertRaises(IntegrityError):
            CheckType.objects.create(name="Diplomacy", category=category)

    def test_inactive_check_types_filtered(self):
        CheckTypeFactory(name="Active", is_active=True)
        CheckTypeFactory(name="Inactive", is_active=False)

        active = CheckType.objects.filter(is_active=True)
        assert active.count() == 1
        assert active.first().name == "Active"


class CheckTypeTraitTests(TestCase):
    """Test CheckTypeTrait model."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="Seduction")
        cls.charm, _ = Trait.objects.get_or_create(
            name="test_charm_ctt",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.SOCIAL},
        )
        cls.allure, _ = Trait.objects.get_or_create(
            name="test_allure_ctt",
            defaults={"trait_type": TraitType.SKILL, "category": TraitCategory.SOCIAL},
        )

    def test_str_representation(self):
        ctt = CheckTypeTraitFactory(
            check_type=self.check_type, trait=self.charm, weight=Decimal("1.0")
        )
        assert "Seduction" in str(ctt)
        assert "test_charm_ctt" in str(ctt)

    def test_default_weight_is_one(self):
        ctt = CheckTypeTrait.objects.create(check_type=self.check_type, trait=self.charm)
        assert ctt.weight == Decimal("1.0")

    def test_unique_together_check_type_and_trait(self):
        CheckTypeTrait.objects.create(check_type=self.check_type, trait=self.charm)
        with self.assertRaises(IntegrityError):
            CheckTypeTrait.objects.create(check_type=self.check_type, trait=self.charm)

    def test_fractional_weight(self):
        ctt = CheckTypeTraitFactory(
            check_type=self.check_type,
            trait=self.allure,
            weight=Decimal("0.5"),
        )
        assert ctt.weight == Decimal("0.5")
