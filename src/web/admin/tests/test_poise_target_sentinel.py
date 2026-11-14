"""The Poise modifier target's required-content sentinel (#4720).

Staff author the row; the dashboard lists it until an active modifier target is scoped to
the Composure check. The probe goes by that scope, not by the row's name: production
calls it "Poise", the example seed "poise", and the check seam reads neither.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.checks.factories import CheckTypeFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory


def _resolve() -> rc.ProbeResult:
    """The shipped declaration's own probe, never a hand-copied duplicate."""
    probe = next(
        dep.probe for dep in rc._declarations() if dep.key == "poise-target-scoped-to-composure"
    )
    return probe.resolve(None)


class PoiseTargetProbeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = ModifierCategoryFactory(name="roll_modifier")
        cls.composure = CheckTypeFactory(name="Composure")

    def test_no_target_scoped_to_composure_is_reported(self) -> None:
        result = _resolve()
        self.assertFalse(result.present)
        self.assertIn("No modifier target is scoped to the Composure check", result.detail)

    def test_a_target_named_poise_but_scoped_to_no_check_is_reported(self) -> None:
        ModifierTargetFactory(name="poise", category=self.category)
        self.assertFalse(_resolve().present)

    def test_a_target_scoped_to_another_check_is_reported(self) -> None:
        ModifierTargetFactory(
            name="poise",
            category=self.category,
            target_check_type=CheckTypeFactory(name="Intimidation"),
        )
        self.assertFalse(_resolve().present)

    def test_an_inactive_target_is_reported_by_name(self) -> None:
        ModifierTargetFactory(
            name="Poise",
            category=self.category,
            target_check_type=self.composure,
            is_active=False,
        )
        result = _resolve()
        self.assertFalse(result.present)
        self.assertIn("(Poise) is inactive", result.detail)

    def test_the_target_closes_the_gap_whatever_it_is_named(self) -> None:
        """Production names it "Poise", capitalised; a lowercase lookup missed it."""
        ModifierTargetFactory(
            name="Poise", category=self.category, target_check_type=self.composure
        )
        self.assertTrue(_resolve().present)
