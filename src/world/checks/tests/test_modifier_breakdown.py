"""Tests for modifier provenance dataclasses."""

from django.test import TestCase

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierBreakdown, ModifierContribution


class ModifierBreakdownTests(TestCase):
    """Test ModifierBreakdown totals and source provenance."""

    def test_modifier_breakdown_totals_and_lists_sources(self):
        b = ModifierBreakdown(
            contributions=[
                ModifierContribution(ModifierSourceKind.CONDITION, "Wounded (severe)", -4),
                ModifierContribution(ModifierSourceKind.ROLLMOD, "Roll modifier", 2),
            ]
        )
        assert b.total == -2
        assert [c.source_label for c in b.contributions] == ["Wounded (severe)", "Roll modifier"]
