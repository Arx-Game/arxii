"""Tests for mechanics type definitions."""

from django.test import SimpleTestCase

from world.mechanics.types import ModifierBreakdown, ModifierSourceDetail


class TestModifierSourceDetail(SimpleTestCase):
    """Tests for ModifierSourceDetail dataclass."""

    def test_create_source_detail(self):
        """Can create a ModifierSourceDetail with all fields."""
        detail = ModifierSourceDetail(
            source_name="Attractive",
            base_value=10,
            amplification=2,
            final_value=12,
            is_amplifier=False,
            blocked_by_immunity=False,
        )
        assert detail.source_name == "Attractive"
        assert detail.base_value == 10
        assert detail.amplification == 2
        assert detail.final_value == 12
        assert detail.is_amplifier is False
        assert detail.blocked_by_immunity is False


class TestModifierBreakdown(SimpleTestCase):
    """Tests for ModifierBreakdown dataclass."""

    def test_create_breakdown(self):
        """Can create a ModifierBreakdown with sources."""
        source = ModifierSourceDetail(
            source_name="Test",
            base_value=5,
            amplification=0,
            final_value=5,
            is_amplifier=False,
            blocked_by_immunity=False,
        )
        breakdown = ModifierBreakdown(
            modifier_type_name="Allure",
            sources=[source],
            total=5,
            has_immunity=False,
            negatives_blocked=0,
        )
        assert breakdown.modifier_type_name == "Allure"
        assert len(breakdown.sources) == 1
        assert breakdown.total == 5
        assert breakdown.has_immunity is False
