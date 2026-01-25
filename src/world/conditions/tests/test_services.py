"""
Tests for conditions service layer.
"""

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.constants import (
    CapabilityEffectType,
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    CheckTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionCategoryFactory,
    ConditionCheckModifierFactory,
    ConditionConditionInteractionFactory,
    ConditionDamageInteractionFactory,
    ConditionDamageOverTimeFactory,
    ConditionInstanceFactory,
    ConditionResistanceModifierFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import (
    ConditionInstance,
)
from world.conditions.services import (
    apply_condition,
    clear_all_conditions,
    get_active_conditions,
    get_aggro_priority,
    get_capability_status,
    get_check_modifier,
    get_resistance_modifier,
    get_turn_order_modifier,
    has_condition,
    process_damage_interactions,
    process_round_end,
    process_round_start,
    remove_condition,
    remove_conditions_by_category,
    suppress_condition,
    unsuppress_condition,
)


class GetActiveConditionsTest(TestCase):
    """Tests for get_active_conditions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.category1 = ConditionCategoryFactory(name="debuff", is_negative=True)
        cls.category2 = ConditionCategoryFactory(name="buff", is_negative=False)

        cls.condition1 = ConditionTemplateFactory(name="burning", category=cls.category1)
        cls.condition2 = ConditionTemplateFactory(name="empowered", category=cls.category2)

    def test_get_active_conditions_empty(self):
        """Test getting conditions when none exist."""
        conditions = get_active_conditions(self.target)
        assert conditions.count() == 0

    def test_get_active_conditions_returns_instances(self):
        """Test getting active condition instances."""
        ConditionInstanceFactory(target=self.target, condition=self.condition1)
        ConditionInstanceFactory(target=self.target, condition=self.condition2)

        conditions = get_active_conditions(self.target)
        assert conditions.count() == 2

    def test_get_active_conditions_filter_by_category(self):
        """Test filtering conditions by category."""
        ConditionInstanceFactory(target=self.target, condition=self.condition1)
        ConditionInstanceFactory(target=self.target, condition=self.condition2)

        conditions = get_active_conditions(self.target, category=self.category1)
        assert conditions.count() == 1
        assert conditions.first().condition == self.condition1

    def test_get_active_conditions_filter_by_condition(self):
        """Test filtering conditions by specific condition template."""
        ConditionInstanceFactory(target=self.target, condition=self.condition1)
        ConditionInstanceFactory(target=self.target, condition=self.condition2)

        conditions = get_active_conditions(self.target, condition=self.condition1)
        assert conditions.count() == 1
        assert conditions.first().condition == self.condition1

    def test_get_active_conditions_excludes_suppressed(self):
        """Test that suppressed conditions are excluded by default."""
        ConditionInstanceFactory(target=self.target, condition=self.condition1, is_suppressed=False)
        ConditionInstanceFactory(target=self.target, condition=self.condition2, is_suppressed=True)

        conditions = get_active_conditions(self.target)
        assert conditions.count() == 1

        conditions_with_suppressed = get_active_conditions(self.target, include_suppressed=True)
        assert conditions_with_suppressed.count() == 2


class HasConditionTest(TestCase):
    """Tests for has_condition service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.condition = ConditionTemplateFactory(name="frozen")

    def test_has_condition_false_when_absent(self):
        """Test has_condition returns False when condition not present."""
        assert has_condition(self.target, self.condition) is False

    def test_has_condition_true_when_present(self):
        """Test has_condition returns True when condition present."""
        ConditionInstanceFactory(target=self.target, condition=self.condition)

        assert has_condition(self.target, self.condition) is True

    def test_has_condition_ignores_suppressed_by_default(self):
        """Test has_condition ignores suppressed conditions by default."""
        ConditionInstanceFactory(target=self.target, condition=self.condition, is_suppressed=True)

        assert has_condition(self.target, self.condition) is False
        assert has_condition(self.target, self.condition, include_suppressed=True) is True


class ApplyConditionTest(TestCase):
    """Tests for apply_condition service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.source = ObjectDB.objects.create(db_key="SourceCharacter")
        cls.condition = ConditionTemplateFactory(
            name="burning",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )

    def test_apply_condition_creates_instance(self):
        """Test applying a new condition creates an instance."""
        result = apply_condition(self.target, self.condition)

        assert result.success is True
        assert result.instance is not None
        assert result.instance.condition == self.condition
        assert result.instance.target == self.target
        assert result.instance.rounds_remaining == 3
        assert result.stacks_added == 1

    def test_apply_condition_with_severity(self):
        """Test applying condition with custom severity."""
        result = apply_condition(self.target, self.condition, severity=5)

        assert result.success is True
        assert result.instance.severity == 5

    def test_apply_condition_with_duration_override(self):
        """Test applying condition with custom duration."""
        result = apply_condition(self.target, self.condition, duration_rounds=10)

        assert result.success is True
        assert result.instance.rounds_remaining == 10

    def test_apply_condition_with_source(self):
        """Test applying condition with source tracking."""
        result = apply_condition(
            self.target,
            self.condition,
            source_character=self.source,
            source_description="Fireball spell",
        )

        assert result.success is True
        assert result.instance.source_character == self.source
        assert result.instance.source_description == "Fireball spell"

    def test_apply_condition_refreshes_non_stackable(self):
        """Test applying non-stackable condition refreshes existing."""
        # Apply once
        apply_condition(self.target, self.condition, severity=2)

        # Apply again with higher severity
        result = apply_condition(self.target, self.condition, severity=5)

        assert result.success is True
        assert "refreshed" in result.message
        assert result.instance.severity == 5

        # Only one instance should exist
        assert ConditionInstance.objects.filter(target=self.target).count() == 1

    def test_apply_condition_stacks_when_stackable(self):
        """Test applying stackable condition adds stacks."""
        stackable = ConditionTemplateFactory(
            name="bleeding",
            is_stackable=True,
            max_stacks=5,
            stack_behavior=StackBehavior.INTENSITY,
        )

        # Apply first time
        apply_condition(self.target, stackable)

        # Apply second time
        result = apply_condition(self.target, stackable)

        assert result.success is True
        assert result.stacks_added == 1
        assert result.instance.stacks == 2
        assert "stacked to 2" in result.message

    def test_apply_condition_respects_max_stacks(self):
        """Test that stacking respects max_stacks limit."""
        stackable = ConditionTemplateFactory(
            name="poison",
            is_stackable=True,
            max_stacks=2,
        )

        # Apply to max
        apply_condition(self.target, stackable)
        apply_condition(self.target, stackable)

        # This should not add more stacks
        result = apply_condition(self.target, stackable)

        # Should refresh but not add stack
        assert result.instance.stacks == 2

    def test_apply_condition_duration_stacking(self):
        """Test that duration stacking adds to remaining rounds."""
        stackable = ConditionTemplateFactory(
            name="regenerating",
            is_stackable=True,
            max_stacks=5,
            stack_behavior=StackBehavior.DURATION,
            default_duration_value=3,
        )

        apply_condition(self.target, stackable)
        result = apply_condition(self.target, stackable)

        assert result.instance.rounds_remaining == 6  # 3 + 3


class ApplyConditionProgressionTest(TestCase):
    """Tests for apply_condition with progressive conditions."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.progressive = ConditionTemplateFactory(
            name="poison",
            has_progression=True,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.progressive,
            stage_order=1,
            name="Numbness",
            rounds_to_next=2,
            severity_multiplier=Decimal("1.0"),
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.progressive,
            stage_order=2,
            name="Weakness",
            rounds_to_next=2,
            severity_multiplier=Decimal("1.5"),
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.progressive,
            stage_order=3,
            name="Paralysis",
            rounds_to_next=None,  # Final stage
            severity_multiplier=Decimal("2.0"),
        )

    def test_apply_progressive_condition_starts_at_stage_1(self):
        """Test progressive condition starts at first stage."""
        result = apply_condition(self.target, self.progressive)

        assert result.success is True
        assert result.instance.current_stage == self.stage1
        assert result.instance.stage_rounds_remaining == 2


class ApplyConditionInteractionsTest(TestCase):
    """Tests for condition-condition interactions when applying."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.burning = ConditionTemplateFactory(name="burning")
        cls.wet = ConditionTemplateFactory(name="wet")
        cls.frozen = ConditionTemplateFactory(name="frozen")

        # Wet removes Burning when applied
        ConditionConditionInteractionFactory(
            condition=cls.burning,
            other_condition=cls.wet,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_SELF,
        )

        # Burning prevents Frozen from being applied
        ConditionConditionInteractionFactory(
            condition=cls.burning,
            other_condition=cls.frozen,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )

    def test_apply_condition_removes_existing_via_interaction(self):
        """Test applying condition removes other via interaction."""
        # Apply burning first
        apply_condition(self.target, self.burning)
        assert has_condition(self.target, self.burning)

        # Apply wet - should remove burning
        result = apply_condition(self.target, self.wet)

        assert result.success is True
        assert self.burning in result.removed_conditions

    def test_apply_condition_prevented_by_existing(self):
        """Test applying condition can be prevented by existing condition."""
        # Apply burning first
        apply_condition(self.target, self.burning)

        # Try to apply frozen - should be prevented
        result = apply_condition(self.target, self.frozen)

        assert result.success is False
        assert result.was_prevented is True
        assert result.prevented_by == self.burning


class RemoveConditionTest(TestCase):
    """Tests for remove_condition service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.condition = ConditionTemplateFactory(name="frozen")

    def test_remove_condition_deletes_instance(self):
        """Test removing a condition deletes the instance."""
        ConditionInstanceFactory(target=self.target, condition=self.condition)

        result = remove_condition(self.target, self.condition)

        assert result is True
        assert not has_condition(self.target, self.condition)

    def test_remove_condition_returns_false_when_absent(self):
        """Test removing absent condition returns False."""
        result = remove_condition(self.target, self.condition)

        assert result is False

    def test_remove_condition_single_stack(self):
        """Test removing single stack from stackable condition."""
        stackable = ConditionTemplateFactory(name="bleeding", is_stackable=True)
        instance = ConditionInstanceFactory(target=self.target, condition=stackable, stacks=3)

        result = remove_condition(self.target, stackable, remove_all_stacks=False)

        assert result is True
        instance.refresh_from_db()
        assert instance.stacks == 2

    def test_remove_condition_all_stacks(self):
        """Test removing all stacks from stackable condition."""
        stackable = ConditionTemplateFactory(name="bleeding", is_stackable=True)
        ConditionInstanceFactory(target=self.target, condition=stackable, stacks=3)

        result = remove_condition(self.target, stackable, remove_all_stacks=True)

        assert result is True
        assert not has_condition(self.target, stackable)


class RemoveConditionsByCategoryTest(TestCase):
    """Tests for remove_conditions_by_category service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.debuff_category = ConditionCategoryFactory(name="debuff")
        cls.buff_category = ConditionCategoryFactory(name="buff")

        cls.debuff1 = ConditionTemplateFactory(name="slowed", category=cls.debuff_category)
        cls.debuff2 = ConditionTemplateFactory(name="weakened", category=cls.debuff_category)
        cls.buff = ConditionTemplateFactory(name="empowered", category=cls.buff_category)

    def test_remove_conditions_by_category(self):
        """Test removing all conditions in a category."""
        ConditionInstanceFactory(target=self.target, condition=self.debuff1)
        ConditionInstanceFactory(target=self.target, condition=self.debuff2)
        ConditionInstanceFactory(target=self.target, condition=self.buff)

        removed = remove_conditions_by_category(self.target, self.debuff_category)

        assert len(removed) == 2
        assert self.debuff1 in removed
        assert self.debuff2 in removed
        assert has_condition(self.target, self.buff)  # Buff should remain


class ProcessDamageInteractionsTest(TestCase):
    """Tests for process_damage_interactions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.fire = DamageTypeFactory(name="fire")
        cls.cold = DamageTypeFactory(name="cold")
        cls.force = DamageTypeFactory(name="force")

        cls.frozen = ConditionTemplateFactory(name="frozen")
        cls.wet = ConditionTemplateFactory(name="wet")
        cls.burning = ConditionTemplateFactory(name="burning")

        # Force damage removes Frozen and deals +50% damage
        ConditionDamageInteractionFactory(
            condition=cls.frozen,
            damage_type=cls.force,
            damage_modifier_percent=50,
            removes_condition=True,
        )

        # Fire damage to Wet deals -30% damage
        ConditionDamageInteractionFactory(
            condition=cls.wet,
            damage_type=cls.fire,
            damage_modifier_percent=-30,
            removes_condition=False,
        )

        # Cold damage removes Burning
        ConditionDamageInteractionFactory(
            condition=cls.burning,
            damage_type=cls.cold,
            damage_modifier_percent=0,
            removes_condition=True,
        )

    def test_damage_interaction_modifies_damage(self):
        """Test damage interaction returns damage modifier."""
        ConditionInstanceFactory(target=self.target, condition=self.frozen)

        result = process_damage_interactions(self.target, self.force)

        assert result.damage_modifier_percent == 50

    def test_damage_interaction_removes_condition(self):
        """Test damage interaction can remove condition."""
        ConditionInstanceFactory(target=self.target, condition=self.frozen)

        result = process_damage_interactions(self.target, self.force)

        assert len(result.removed_conditions) == 1
        assert result.removed_conditions[0].condition == self.frozen
        assert not has_condition(self.target, self.frozen)

    def test_damage_interaction_negative_modifier(self):
        """Test damage interaction with negative modifier."""
        ConditionInstanceFactory(target=self.target, condition=self.wet)

        result = process_damage_interactions(self.target, self.fire)

        assert result.damage_modifier_percent == -30

    def test_damage_interaction_cumulative(self):
        """Test multiple damage interactions are cumulative."""
        # Create another condition with fire interaction
        condition2 = ConditionTemplateFactory(name="oiled")
        ConditionDamageInteractionFactory(
            condition=condition2,
            damage_type=self.fire,
            damage_modifier_percent=100,
        )

        ConditionInstanceFactory(target=self.target, condition=self.wet)
        ConditionInstanceFactory(target=self.target, condition=condition2)

        result = process_damage_interactions(self.target, self.fire)

        assert result.damage_modifier_percent == 70  # -30 + 100


class GetCapabilityStatusTest(TestCase):
    """Tests for get_capability_status service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.movement = CapabilityTypeFactory(name="movement")
        cls.speech = CapabilityTypeFactory(name="speech")

        cls.paralyzed = ConditionTemplateFactory(name="paralyzed")
        cls.slowed = ConditionTemplateFactory(name="slowed")

        # Paralyzed blocks movement
        ConditionCapabilityEffectFactory(
            condition=cls.paralyzed,
            capability=cls.movement,
            effect_type=CapabilityEffectType.BLOCKED,
        )

        # Slowed reduces movement by 50%
        ConditionCapabilityEffectFactory(
            condition=cls.slowed,
            capability=cls.movement,
            effect_type=CapabilityEffectType.REDUCED,
            modifier_percent=-50,
        )

    def test_capability_blocked(self):
        """Test capability is blocked by condition."""
        ConditionInstanceFactory(target=self.target, condition=self.paralyzed)

        status = get_capability_status(self.target, self.movement)

        assert status.is_blocked is True
        assert len(status.blocking_conditions) == 1

    def test_capability_reduced(self):
        """Test capability is reduced by condition."""
        ConditionInstanceFactory(target=self.target, condition=self.slowed)

        status = get_capability_status(self.target, self.movement)

        assert status.is_blocked is False
        assert status.modifier_percent == -50


class GetCheckModifierTest(TestCase):
    """Tests for get_check_modifier service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.combat_attack = CheckTypeFactory(name="combat-attack")

        cls.frightened = ConditionTemplateFactory(name="frightened")
        cls.empowered = ConditionTemplateFactory(name="empowered")

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

    def test_check_modifier_single_condition(self):
        """Test check modifier from single condition."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)

        result = get_check_modifier(self.target, self.combat_attack)

        assert result.total_modifier == -20
        assert len(result.breakdown) == 1

    def test_check_modifier_cumulative(self):
        """Test check modifiers are cumulative."""
        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        ConditionInstanceFactory(target=self.target, condition=self.empowered)

        result = get_check_modifier(self.target, self.combat_attack)

        assert result.total_modifier == -5  # -20 + 15
        assert len(result.breakdown) == 2

    def test_check_modifier_scales_with_severity(self):
        """Test check modifier scaling with severity."""
        scaling = ConditionTemplateFactory(name="scaling")
        ConditionCheckModifierFactory(
            condition=scaling,
            check_type=self.combat_attack,
            modifier_value=-5,
            scales_with_severity=True,
        )

        ConditionInstanceFactory(target=self.target, condition=scaling, severity=3)

        result = get_check_modifier(self.target, self.combat_attack)

        assert result.total_modifier == -15  # -5 * 3


class GetResistanceModifierTest(TestCase):
    """Tests for get_resistance_modifier service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.fire = DamageTypeFactory(name="fire")
        cls.lightning = DamageTypeFactory(name="lightning")

        cls.wet = ConditionTemplateFactory(name="wet")

        # Wet gives +50 fire resistance, -50 lightning resistance
        ConditionResistanceModifierFactory(
            condition=cls.wet,
            damage_type=cls.fire,
            modifier_value=50,
        )
        ConditionResistanceModifierFactory(
            condition=cls.wet,
            damage_type=cls.lightning,
            modifier_value=-50,
        )

    def test_resistance_modifier_positive(self):
        """Test positive resistance modifier."""
        ConditionInstanceFactory(target=self.target, condition=self.wet)

        result = get_resistance_modifier(self.target, self.fire)

        assert result.total_modifier == 50

    def test_resistance_modifier_negative(self):
        """Test negative resistance modifier (vulnerability)."""
        ConditionInstanceFactory(target=self.target, condition=self.wet)

        result = get_resistance_modifier(self.target, self.lightning)

        assert result.total_modifier == -50

    def test_resistance_modifier_all_damage(self):
        """Test 'all damage' resistance modifier."""
        warded = ConditionTemplateFactory(name="warded")
        ConditionResistanceModifierFactory(
            condition=warded,
            damage_type=None,  # All damage
            modifier_value=25,
        )

        ConditionInstanceFactory(target=self.target, condition=warded)

        # Should apply to any damage type
        result = get_resistance_modifier(self.target, self.fire)
        assert result.total_modifier == 25

        result = get_resistance_modifier(self.target, self.lightning)
        assert result.total_modifier == 25


class RoundProcessingTest(TestCase):
    """Tests for round processing service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.fire = DamageTypeFactory(name="fire")

        cls.burning = ConditionTemplateFactory(
            name="burning",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )

        # Burning deals 5 fire damage at start of round
        ConditionDamageOverTimeFactory(
            condition=cls.burning,
            damage_type=cls.fire,
            base_damage=5,
            tick_timing=DamageTickTiming.START_OF_ROUND,
            scales_with_severity=True,
            scales_with_stacks=True,
        )

    def test_process_round_start_deals_damage(self):
        """Test round start processes DoT damage."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.burning,
            severity=2,
            rounds_remaining=3,
        )

        result = process_round_start(self.target)

        assert len(result.damage_dealt) == 1
        damage_type, amount = result.damage_dealt[0]
        assert damage_type == self.fire
        assert amount == 10  # 5 base * 2 severity

    def test_process_round_end_decrements_duration(self):
        """Test round end decrements remaining duration."""
        instance = ConditionInstanceFactory(
            target=self.target,
            condition=self.burning,
            rounds_remaining=3,
        )

        process_round_end(self.target)

        instance.refresh_from_db()
        assert instance.rounds_remaining == 2

    def test_process_round_end_expires_condition(self):
        """Test round end expires condition when duration reaches 0."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.burning,
            rounds_remaining=1,
        )

        result = process_round_end(self.target)

        assert len(result.expired_conditions) == 1
        assert not has_condition(self.target, self.burning)

    def test_process_round_end_progresses_stage(self):
        """Test round end progresses condition stage."""
        progressive = ConditionTemplateFactory(name="poison", has_progression=True)
        stage1 = ConditionStageFactory(condition=progressive, stage_order=1, rounds_to_next=1)
        stage2 = ConditionStageFactory(condition=progressive, stage_order=2, rounds_to_next=None)

        instance = ConditionInstanceFactory(
            target=self.target,
            condition=progressive,
            current_stage=stage1,
            stage_rounds_remaining=1,
            rounds_remaining=10,
        )

        result = process_round_end(self.target)

        instance.refresh_from_db()
        assert instance.current_stage == stage2
        assert len(result.progressed_conditions) == 1


class SuppressConditionTest(TestCase):
    """Tests for suppress/unsuppress condition service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.condition = ConditionTemplateFactory(name="poisoned")

    def test_suppress_condition(self):
        """Test suppressing a condition."""
        instance = ConditionInstanceFactory(target=self.target, condition=self.condition)

        result = suppress_condition(self.target, self.condition)

        assert result is True
        instance.refresh_from_db()
        assert instance.is_suppressed is True

    def test_suppress_condition_not_present(self):
        """Test suppressing absent condition returns False."""
        result = suppress_condition(self.target, self.condition)

        assert result is False

    def test_unsuppress_condition(self):
        """Test unsuppressing a condition."""
        instance = ConditionInstanceFactory(
            target=self.target, condition=self.condition, is_suppressed=True
        )

        result = unsuppress_condition(self.target, self.condition)

        assert result is True
        instance.refresh_from_db()
        assert instance.is_suppressed is False


class ClearAllConditionsTest(TestCase):
    """Tests for clear_all_conditions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.debuff_category = ConditionCategoryFactory(name="debuff", is_negative=True)
        cls.buff_category = ConditionCategoryFactory(name="buff", is_negative=False)

        cls.debuff = ConditionTemplateFactory(name="weakened", category=cls.debuff_category)
        cls.buff = ConditionTemplateFactory(name="empowered", category=cls.buff_category)

    def test_clear_all_conditions(self):
        """Test clearing all conditions."""
        ConditionInstanceFactory(target=self.target, condition=self.debuff)
        ConditionInstanceFactory(target=self.target, condition=self.buff)

        count = clear_all_conditions(self.target)

        assert count == 2
        assert ConditionInstance.objects.filter(target=self.target).count() == 0

    def test_clear_only_negative(self):
        """Test clearing only negative conditions."""
        ConditionInstanceFactory(target=self.target, condition=self.debuff)
        ConditionInstanceFactory(target=self.target, condition=self.buff)

        count = clear_all_conditions(self.target, only_negative=True)

        assert count == 1
        assert has_condition(self.target, self.buff)
        assert not has_condition(self.target, self.debuff)

    def test_clear_only_category(self):
        """Test clearing only conditions in a specific category."""
        ConditionInstanceFactory(target=self.target, condition=self.debuff)
        ConditionInstanceFactory(target=self.target, condition=self.buff)

        count = clear_all_conditions(self.target, only_category=self.debuff_category)

        assert count == 1
        assert has_condition(self.target, self.buff)


class CombatModifiersTest(TestCase):
    """Tests for combat-related modifier functions."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")

        cls.hasted = ConditionTemplateFactory(
            name="hasted",
            affects_turn_order=True,
            turn_order_modifier=5,
        )
        cls.slowed = ConditionTemplateFactory(
            name="slowed",
            affects_turn_order=True,
            turn_order_modifier=-3,
        )
        cls.taunted = ConditionTemplateFactory(
            name="taunted",
            draws_aggro=True,
            aggro_priority=10,
        )

    def test_get_turn_order_modifier(self):
        """Test getting turn order modifier."""
        ConditionInstanceFactory(target=self.target, condition=self.hasted)
        ConditionInstanceFactory(target=self.target, condition=self.slowed)

        modifier = get_turn_order_modifier(self.target)

        assert modifier == 2  # 5 - 3

    def test_get_aggro_priority(self):
        """Test getting aggro priority."""
        ConditionInstanceFactory(target=self.target, condition=self.taunted)

        priority = get_aggro_priority(self.target)

        assert priority == 10


class StageSpecificEffectsTest(TestCase):
    """Tests for stage-specific condition effects."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.movement = CapabilityTypeFactory(name="movement")

        cls.poison = ConditionTemplateFactory(name="paralytic-poison", has_progression=True)
        cls.stage1 = ConditionStageFactory(
            condition=cls.poison,
            stage_order=1,
            name="Numbness",
            rounds_to_next=2,
            severity_multiplier=Decimal("1.0"),
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.poison,
            stage_order=2,
            name="Weakness",
            rounds_to_next=2,
            severity_multiplier=Decimal("1.5"),
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.poison,
            stage_order=3,
            name="Paralysis",
            rounds_to_next=None,
            severity_multiplier=Decimal("2.0"),
        )

        # Stage 1: -25% movement (stage-specific, condition=None)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage1,
            capability=cls.movement,
            effect_type=CapabilityEffectType.REDUCED,
            modifier_percent=-25,
        )

        # Stage 2: -50% movement (stage-specific, condition=None)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage2,
            capability=cls.movement,
            effect_type=CapabilityEffectType.REDUCED,
            modifier_percent=-50,
        )

        # Stage 3: movement blocked (stage-specific, condition=None)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage3,
            capability=cls.movement,
            effect_type=CapabilityEffectType.BLOCKED,
        )

    def test_stage_1_effect(self):
        """Test effect at stage 1."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage1,
        )

        status = get_capability_status(self.target, self.movement)

        assert status.is_blocked is False
        assert status.modifier_percent == -25

    def test_stage_2_effect(self):
        """Test effect at stage 2."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage2,
        )

        status = get_capability_status(self.target, self.movement)

        assert status.is_blocked is False
        assert status.modifier_percent == -75  # -50 * 1.5 severity multiplier

    def test_stage_3_effect(self):
        """Test effect at stage 3 (blocked)."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage3,
        )

        status = get_capability_status(self.target, self.movement)

        assert status.is_blocked is True
