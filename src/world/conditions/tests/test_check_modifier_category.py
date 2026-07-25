"""Tests for ConditionCheckModifier category targeting (#2697).

A category-targeted ConditionCheckModifier (check_category set, check_type null)
matches any CheckType in that category — including per-character magic checks
that can't be named by exact FK.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionCheckModifier


class ConditionCheckModifierCategoryTargetingTest(TestCase):
    """Category-level targeting lets a modifier match any check in a category."""

    def test_check_category_only_is_valid(self):
        """A row with check_category set and check_type null is valid."""
        category = CheckCategoryFactory(name="Magic")
        condition = ConditionTemplateFactory()
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=None,
            check_category=category,
            modifier_value=-10,
        )
        mod.full_clean()  # should not raise

    def test_check_type_only_is_valid(self):
        """A row with check_type set and check_category null is valid (backward compat)."""
        check_type = CheckTypeFactory()
        condition = ConditionTemplateFactory()
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=check_type,
            check_category=None,
            modifier_value=-10,
        )
        mod.full_clean()

    def test_both_set_raises_validation_error(self):
        """Setting both check_type and check_category is invalid."""
        check_type = CheckTypeFactory()
        category = CheckCategoryFactory(name="Magic")
        condition = ConditionTemplateFactory()
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=check_type,
            check_category=category,
            modifier_value=-10,
        )
        with self.assertRaises(ValidationError):
            mod.full_clean()

    def test_neither_set_raises_validation_error(self):
        """Setting neither check_type nor check_category is invalid."""
        condition = ConditionTemplateFactory()
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=None,
            check_category=None,
            modifier_value=-10,
        )
        with self.assertRaises(ValidationError):
            mod.full_clean()

    def test_str_shows_category_when_check_type_is_null(self):
        """__str__ displays the category name for category-targeted rows."""
        category = CheckCategoryFactory(name="Magic")
        condition = ConditionTemplateFactory(name="Blinded")
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=None,
            check_category=category,
            modifier_value=-10,
        )
        rendered = str(mod)
        self.assertIn("Blinded", rendered)
        self.assertIn("Magic", rendered)
        self.assertIn("category", rendered.lower())

    def test_str_shows_check_type_when_set(self):
        """__str__ still displays check_type.name for exact-FK rows (backward compat)."""
        check_type = CheckTypeFactory(name="Stealth")
        condition = ConditionTemplateFactory(name="Blinded")
        mod = ConditionCheckModifier(
            condition=condition,
            check_type=check_type,
            check_category=None,
            modifier_value=-10,
        )
        rendered = str(mod)
        self.assertIn("Blinded", rendered)
        self.assertIn("Stealth", rendered)
