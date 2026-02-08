"""Tests for check system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.models import CheckCategory, CheckType


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
