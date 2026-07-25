"""Integration test: a category-targeted ConditionCheckModifier modifies a standalone cast (#2697).

Verifies the full chain end-to-end:
  ConditionCheckModifier(check_category=<category>)
  → get_check_modifier matches the check by category
  → condition_contributions returns the modifier
  → collect_check_modifiers folds it into the breakdown
  → _resolve_cast passes it as extra_modifiers to start_action_resolution
  → perform_check receives it

The test patches perform_check to capture the extra_modifiers argument rather
than running the full check pipeline, isolating the modifier-folding behavior.
"""

from unittest.mock import patch

from django.test.utils import tag

from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


@tag("postgres")
class CategoryConditionModifiesCastTest(CastScenarioMixin):
    """A category-targeted ConditionCheckModifier applies to a standalone technique cast."""

    def test_category_modifier_reaches_cast_check(self):
        """The category-targeted modifier appears in the cast's extra_modifiers."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        # The cast will roll the technique's action_template.check_type (the
        # caster has no provisioned per-character magic check in this test).
        # Author a condition that targets that check's CATEGORY — not the
        # specific check_type — so the category-matching path is exercised.
        template_check = technique.action_template.check_type
        check_category = template_check.category

        blinded = ConditionTemplateFactory(name="blinded-cast-e2e")
        ConditionCheckModifierFactory(
            condition=blinded,
            check_type=None,
            check_category=check_category,
            modifier_value=-15,
        )
        ConditionInstanceFactory(
            target=self.caster.character_sheet.character,
            condition=blinded,
        )

        # Patch perform_check to capture extra_modifiers without running the
        # full check pipeline.
        captured = {}

        from world.checks.services import perform_check

        original_perform_check = perform_check

        def capture_perform_check(character, check_type, target_difficulty=0, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return original_perform_check(character, check_type, target_difficulty, **kwargs)

        with patch("actions.services.perform_check", side_effect=capture_perform_check):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                target_persona=None,
                technique=technique,
                confirm_soulfray_risk=True,
            )

        # The -15 modifier should have been folded into extra_modifiers.
        assert "extra_modifiers" in captured, "perform_check was never called"
        assert captured["extra_modifiers"] <= -15, (
            f"Expected extra_modifiers <= -15 (condition penalty folded in), "
            f"got {captured['extra_modifiers']}"
        )

    def test_exact_fk_modifier_reaches_cast_check(self):
        """An exact-FK ConditionCheckModifier also reaches the cast (regression)."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        template_check = technique.action_template.check_type

        focused = ConditionTemplateFactory(name="focused-cast-e2e")
        ConditionCheckModifierFactory(
            condition=focused,
            check_type=template_check,
            check_category=None,
            modifier_value=10,
        )
        ConditionInstanceFactory(
            target=self.caster.character_sheet.character,
            condition=focused,
        )

        captured = {}

        from world.checks.services import perform_check

        original_perform_check = perform_check

        def capture_perform_check(character, check_type, target_difficulty=0, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return original_perform_check(character, check_type, target_difficulty, **kwargs)

        with patch("actions.services.perform_check", side_effect=capture_perform_check):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                target_persona=None,
                technique=technique,
                confirm_soulfray_risk=True,
            )

        assert "extra_modifiers" in captured, "perform_check was never called"
        assert captured["extra_modifiers"] >= 10, (
            f"Expected extra_modifiers >= 10 (condition bonus folded in), "
            f"got {captured['extra_modifiers']}"
        )
