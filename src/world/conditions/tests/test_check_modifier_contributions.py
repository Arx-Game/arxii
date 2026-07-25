"""
Tests for condition_contributions() adapter function.

Verifies that condition_contributions() maps get_check_modifier()'s breakdown
into a list[ModifierContribution] with CONDITION source_kind, without
reimplementing get_check_modifier's logic.
"""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import condition_contributions, get_check_modifier


class ConditionContributionsTest(TestCase):
    """Tests for condition_contributions() adapter."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDBFactory(db_key="ContribTarget")
        CharacterSheetFactory(character=cls.target)
        cls.combat_attack = CheckTypeFactory(name="combat-attack-contrib")

        cls.frightened = ConditionTemplateFactory(name="frightened-contrib")
        cls.empowered = ConditionTemplateFactory(name="empowered-contrib")

        # Frightened gives -20 to combat attack
        ConditionCheckModifierFactory(
            condition=cls.frightened,
            check_type=cls.combat_attack,
            modifier_value=-20,
        )

        # Empowered gives +15 to combat attack
        ConditionCheckModifierFactory(
            condition=cls.empowered,
            check_type=cls.combat_attack,
            modifier_value=15,
        )

    def test_empty_when_no_conditions(self):
        """No active conditions → empty list."""
        result = condition_contributions(self.target.sheet_data, self.combat_attack)
        assert result == []

    def test_single_condition_maps_to_contribution(self):
        """Single condition produces one contribution with CONDITION source_kind."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)

        assert len(contributions) == 1
        c = contributions[0]
        assert c.source_kind == ModifierSourceKind.CONDITION
        assert c.value == -20
        assert c.source_label == "frightened-contrib"

    def test_multiple_conditions_map_1to1_with_breakdown(self):
        """Contributions are 1:1 with get_check_modifier().breakdown."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        ConditionInstanceFactory(target=self.target, condition=self.empowered)

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)
        breakdown = get_check_modifier(self.target.sheet_data, self.combat_attack).breakdown

        assert len(contributions) == len(breakdown)
        for contrib, (_, mod_value) in zip(contributions, breakdown, strict=True):
            assert contrib.source_kind == ModifierSourceKind.CONDITION
            assert contrib.value == mod_value

    def test_all_contributions_have_condition_source_kind(self):
        """Every contribution has source_kind == CONDITION."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        ConditionInstanceFactory(target=self.target, condition=self.empowered)

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)

        assert all(c.source_kind == ModifierSourceKind.CONDITION for c in contributions)

    def test_values_match_breakdown_values(self):
        """Contribution values match get_check_modifier breakdown int values."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)
        modifier_result = get_check_modifier(self.target.sheet_data, self.combat_attack)

        assert len(contributions) == 1
        assert contributions[0].value == modifier_result.breakdown[0][1]


class ConditionContributionsWithStageTest(TestCase):
    """Tests for condition_contributions() when a condition has an active stage."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDBFactory(db_key="StageContribTarget")
        CharacterSheetFactory(character=cls.target)
        cls.combat_attack = CheckTypeFactory(name="combat-attack-stage-contrib")

        cls.poison = ConditionTemplateFactory(
            name="paralytic-poison-contrib",
            has_progression=True,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.poison,
            stage_order=1,
            name="Numbness",
            rounds_to_next=2,
            severity_multiplier=Decimal("1.0"),
        )

        # Attach check modifier to the condition (applies at all stages)
        ConditionCheckModifierFactory(
            condition=cls.poison,
            check_type=cls.combat_attack,
            modifier_value=-10,
        )

    def test_label_includes_stage_name_when_present(self):
        """source_label includes stage name in parentheses when stage is active."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage1,
        )

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)

        assert len(contributions) == 1
        assert contributions[0].source_label == "paralytic-poison-contrib (Numbness)"

    def test_label_is_template_name_only_when_no_stage(self):
        """source_label is just the template name when no stage is active."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=None,
        )

        contributions = condition_contributions(self.target.sheet_data, self.combat_attack)

        assert len(contributions) == 1
        assert contributions[0].source_label == "paralytic-poison-contrib"


class CategoryTargetingGetCheckModifierTest(TestCase):
    """get_check_modifier matches category-targeted rows (#2697).

    A ConditionCheckModifier with check_category set (check_type null) matches
    any CheckType in that category — including per-character magic checks.
    """

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDBFactory(db_key="CategoryTarget")
        CharacterSheetFactory(character=cls.target)
        cls.magic_category = CheckCategoryFactory(name="Magic")
        cls.combat_category = CheckCategoryFactory(name="Combat")
        cls.magic_check = CheckTypeFactory(name="magic-check-cat", category=cls.magic_category)
        cls.combat_check = CheckTypeFactory(name="combat-check-cat", category=cls.combat_category)

        cls.blinded = ConditionTemplateFactory(name="blinded-cat")
        cls.focused = ConditionTemplateFactory(name="focused-cat")

        # Blinded: -15 to ALL Magic-category checks (category-targeted)
        ConditionCheckModifierFactory(
            condition=cls.blinded,
            check_type=None,
            check_category=cls.magic_category,
            modifier_value=-15,
        )
        # Focused: +10 to the specific magic_check (exact-FK, for stacking test)
        ConditionCheckModifierFactory(
            condition=cls.focused,
            check_type=cls.magic_check,
            check_category=None,
            modifier_value=10,
        )

    def test_category_targeted_modifier_matches_check_in_category(self):
        """A check_category row matches a CheckType in that category."""
        ConditionInstanceFactory(target=self.target, condition=self.blinded)

        result = get_check_modifier(self.target.sheet_data, self.magic_check)
        assert result.total_modifier == -15

    def test_category_targeted_modifier_does_not_match_other_category(self):
        """A check_category row does NOT match a CheckType in a different category."""
        ConditionInstanceFactory(target=self.target, condition=self.blinded)

        result = get_check_modifier(self.target.sheet_data, self.combat_check)
        assert result.total_modifier == 0

    def test_exact_fk_match_still_works(self):
        """An exact check_type row still matches by FK (regression)."""
        ConditionInstanceFactory(target=self.target, condition=self.focused)

        result = get_check_modifier(self.target.sheet_data, self.magic_check)
        assert result.total_modifier == 10

    def test_both_exact_and_category_rows_stack(self):
        """When both an exact-FK and a category row exist, both modifiers apply."""
        ConditionInstanceFactory(target=self.target, condition=self.blinded)
        ConditionInstanceFactory(target=self.target, condition=self.focused)

        result = get_check_modifier(self.target.sheet_data, self.magic_check)
        assert result.total_modifier == -15 + 10  # -5
