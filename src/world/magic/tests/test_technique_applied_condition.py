"""Tests for TechniqueAppliedCondition through model with formula scaling."""

from decimal import Decimal

from evennia.utils.test_resources import EvenniaTestCase


class TechniqueAppliedConditionTests(EvenniaTestCase):
    def test_compute_severity_formula(self):
        from world.magic.factories import TechniqueAppliedConditionFactory

        ac = TechniqueAppliedConditionFactory(
            base_severity=2,
            severity_intensity_multiplier=Decimal("0.5"),
            severity_per_extra_sl=1,
            minimum_success_level=1,
        )
        # SL=1 (at threshold): 2 + floor(0.5 * 4) + 1*0 = 4
        self.assertEqual(ac.compute_severity(effective_intensity=4, success_level=1), 4)
        # SL=3: 2 + floor(0.5 * 4) + 1*2 = 6
        self.assertEqual(ac.compute_severity(effective_intensity=4, success_level=3), 6)

    def test_compute_duration_falls_back_to_template(self):
        from world.magic.factories import TechniqueAppliedConditionFactory

        ac = TechniqueAppliedConditionFactory(
            base_duration_rounds=None,
            duration_intensity_multiplier=Decimal(0),
            duration_per_extra_sl=0,
            minimum_success_level=1,
        )
        ac.condition.default_duration_value = 5
        ac.condition.save(update_fields=["default_duration_value"])
        self.assertEqual(
            ac.compute_duration_rounds(effective_intensity=10, success_level=2),
            5,
        )
