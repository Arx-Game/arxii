"""The poise modifier target's required-content sentinel (#4720).

The seed only looks the row up on production, so staff author it; the dashboard lists it
until a ``poise`` target exists in ``roll_modifier`` and is scoped to the Composure check.
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

    def test_no_poise_target_is_reported(self) -> None:
        result = _resolve()
        self.assertFalse(result.present)
        self.assertIn("No modifier target named poise", result.detail)

    def test_a_poise_target_scoped_to_no_check_is_reported(self) -> None:
        ModifierTargetFactory(name="poise", category=self.category)
        result = _resolve()
        self.assertFalse(result.present)
        self.assertIn("not Composure", result.detail)

    def test_a_poise_target_scoped_to_another_check_is_reported(self) -> None:
        ModifierTargetFactory(
            name="poise",
            category=self.category,
            target_check_type=CheckTypeFactory(name="Intimidation"),
        )
        self.assertFalse(_resolve().present)

    def test_an_inactive_poise_target_is_reported(self) -> None:
        ModifierTargetFactory(
            name="poise",
            category=self.category,
            target_check_type=self.composure,
            is_active=False,
        )
        self.assertFalse(_resolve().present)

    def test_a_poise_target_scoped_to_composure_closes_the_gap(self) -> None:
        ModifierTargetFactory(
            name="poise", category=self.category, target_check_type=self.composure
        )
        self.assertTrue(_resolve().present)
