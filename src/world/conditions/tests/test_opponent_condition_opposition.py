"""Tests for opponent_condition_opposition() and its extracted core,
_check_modifier_for_target() (#3384).

The condition system's check-modifier channel (get_check_modifier /
condition_contributions) only ever reached a CharacterSheet-owning bearer.
opponent_condition_opposition() is the ObjectDB-keyed sibling that lets an
ephemeral CombatOpponent (no CharacterSheet, ADR-0038) read the SAME
ConditionCheckModifier rows -- these tests pin that it reads identically to
get_check_modifier for a target that DOES have a sheet, and that it works for
one that does not.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import get_check_modifier, opponent_condition_opposition


class OpponentConditionOppositionTest(TestCase):
    """Tests for opponent_condition_opposition() -- #3384."""

    @classmethod
    def setUpTestData(cls):
        # Deliberately NO CharacterSheet -- this is the whole point: an
        # ephemeral CombatOpponent's ObjectDB has none (ADR-0038).
        cls.opponent = ObjectDBFactory(db_key="OpponentTarget")
        cls.combat_category = CheckCategoryFactory(name="opponent-opposition-combat")
        cls.combat_attack = CheckTypeFactory(
            name="opponent-opposition-attack", category=cls.combat_category
        )

        cls.staggered = ConditionTemplateFactory(name="staggered-opposition")
        ConditionCheckModifierFactory(
            condition=cls.staggered,
            check_type=cls.combat_attack,
            modifier_value=-15,
        )

        cls.category_scoped = ConditionTemplateFactory(name="category-scoped-opposition")
        ConditionCheckModifierFactory(
            condition=cls.category_scoped,
            check_type=None,
            check_category=cls.combat_category,
            modifier_value=-8,
        )

    def test_no_active_conditions_is_zero(self):
        """No conditions on the opponent -> 0, no query blows up on a sheet-less target."""
        assert opponent_condition_opposition(self.opponent, self.combat_attack) == 0

    def test_reads_a_check_type_scoped_condition(self):
        ConditionInstanceFactory(target=self.opponent, condition=self.staggered)

        assert opponent_condition_opposition(self.opponent, self.combat_attack) == -15

    def test_reads_a_check_category_scoped_condition(self):
        ConditionInstanceFactory(target=self.opponent, condition=self.category_scoped)

        assert opponent_condition_opposition(self.opponent, self.combat_attack) == -8

    def test_no_sign_flip_penalty_stays_negative(self):
        """Spec decision #2: a penalty condition (negative modifier_value) is summed
        as-authored -- no negation -- so it LOWERS the total it feeds into."""
        ConditionInstanceFactory(target=self.opponent, condition=self.staggered)

        result = opponent_condition_opposition(self.opponent, self.combat_attack)

        assert result < 0
        assert result == -15

    def test_scales_with_severity(self):
        scaling = ConditionTemplateFactory(name="scaling-opposition")
        ConditionCheckModifierFactory(
            condition=scaling,
            check_type=self.combat_attack,
            modifier_value=-5,
            scales_with_severity=True,
        )
        ConditionInstanceFactory(target=self.opponent, condition=scaling, severity=3)

        assert opponent_condition_opposition(self.opponent, self.combat_attack) == -15

    def test_scales_with_stage(self):
        staged = ConditionTemplateFactory(name="staged-opposition")
        stage = ConditionStageFactory(condition=staged, severity_multiplier=2)
        ConditionCheckModifierFactory(
            condition=staged,
            check_type=self.combat_attack,
            modifier_value=-5,
        )
        ConditionInstanceFactory(target=self.opponent, condition=staged, current_stage=stage)

        assert opponent_condition_opposition(self.opponent, self.combat_attack) == -10

    def test_cumulative_across_multiple_conditions(self):
        ConditionInstanceFactory(target=self.opponent, condition=self.staggered)
        ConditionInstanceFactory(target=self.opponent, condition=self.category_scoped)

        assert opponent_condition_opposition(self.opponent, self.combat_attack) == -23

    def test_matches_get_check_modifier_for_a_sheet_owning_target(self):
        """_check_modifier_for_target is the shared core -- for a target that DOES own
        a CharacterSheet, opponent_condition_opposition must agree exactly with
        get_check_modifier's total_modifier (byte-identical extraction, #3384)."""
        sheeted = ObjectDBFactory(db_key="SheetedOpponentTarget")
        CharacterSheetFactory(character=sheeted)
        ConditionInstanceFactory(target=sheeted, condition=self.staggered)
        ConditionInstanceFactory(target=sheeted, condition=self.category_scoped)

        via_sheet = get_check_modifier(sheeted.sheet_data, self.combat_attack).total_modifier
        via_objectdb = opponent_condition_opposition(sheeted, self.combat_attack)

        assert via_sheet == via_objectdb == -23
