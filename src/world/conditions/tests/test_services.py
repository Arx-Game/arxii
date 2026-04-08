"""
Tests for conditions service layer.
"""

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
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
    _build_bulk_context,
    advance_condition_severity,
    apply_condition,
    bulk_apply_conditions,
    clear_all_conditions,
    get_active_conditions,
    get_aggro_priority,
    get_all_capability_values,
    get_capability_status,
    get_capability_value,
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
    """Tests for get_capability_status and related functions."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.movement = CapabilityTypeFactory(name="movement")
        cls.speech = CapabilityTypeFactory(name="speech")

        cls.paralyzed = ConditionTemplateFactory(name="paralyzed")
        cls.slowed = ConditionTemplateFactory(name="slowed")
        cls.hasted = ConditionTemplateFactory(name="hasted")

        # Paralyzed: large negative effectively blocks movement
        ConditionCapabilityEffectFactory(
            condition=cls.paralyzed,
            capability=cls.movement,
            value=-100,
        )

        # Slowed: reduces movement
        ConditionCapabilityEffectFactory(
            condition=cls.slowed,
            capability=cls.movement,
            value=-5,
        )

        # Hasted: enhances movement
        ConditionCapabilityEffectFactory(
            condition=cls.hasted,
            capability=cls.movement,
            value=10,
        )

    def test_capability_effectively_blocked(self):
        """Large negative value floors to 0 (effectively blocked)."""
        ConditionInstanceFactory(target=self.target, condition=self.paralyzed)

        status = get_capability_status(self.target, self.movement)

        assert status.value == 0
        assert len(status.condition_contributions) == 1

    def test_capability_reduced(self):
        """Negative value reduces capability."""
        ConditionInstanceFactory(target=self.target, condition=self.slowed)

        status = get_capability_status(self.target, self.movement)

        # -5 floors to 0 since there's no base value
        assert status.value == 0
        assert len(status.condition_contributions) == 1
        # The raw contribution is -5
        assert status.condition_contributions[0][1] == -5

    def test_capability_enhanced(self):
        """Positive value enhances capability."""
        ConditionInstanceFactory(target=self.target, condition=self.hasted)

        status = get_capability_status(self.target, self.movement)

        assert status.value == 10
        assert len(status.condition_contributions) == 1

    def test_capability_stacking(self):
        """Multiple conditions stack additively."""
        ConditionInstanceFactory(target=self.target, condition=self.hasted)
        ConditionInstanceFactory(target=self.target, condition=self.slowed)

        status = get_capability_status(self.target, self.movement)

        # 10 + (-5) = 5
        assert status.value == 5
        assert len(status.condition_contributions) == 2

    def test_no_conditions_returns_zero(self):
        """No conditions means capability value is 0."""
        status = get_capability_status(self.target, self.movement)

        assert status.value == 0
        assert len(status.condition_contributions) == 0

    def test_unrelated_capability_unaffected(self):
        """Conditions on movement don't affect speech."""
        ConditionInstanceFactory(target=self.target, condition=self.paralyzed)

        status = get_capability_status(self.target, self.speech)

        assert status.value == 0
        assert len(status.condition_contributions) == 0

    def test_floor_at_zero(self):
        """Value can never go below 0."""
        ConditionInstanceFactory(target=self.target, condition=self.paralyzed)
        ConditionInstanceFactory(target=self.target, condition=self.slowed)

        status = get_capability_status(self.target, self.movement)

        # -100 + (-5) = -105, floored to 0
        assert status.value == 0


class GetCapabilityValueTest(TestCase):
    """Tests for get_capability_value convenience function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.flight = CapabilityTypeFactory(name="flight")
        cls.buffed = ConditionTemplateFactory(name="wings")

        ConditionCapabilityEffectFactory(
            condition=cls.buffed,
            capability=cls.flight,
            value=15,
        )

    def test_returns_value(self):
        """get_capability_value returns just the integer."""
        ConditionInstanceFactory(target=self.target, condition=self.buffed)
        assert get_capability_value(self.target, self.flight) == 15

    def test_no_conditions_returns_zero(self):
        """No conditions means 0."""
        assert get_capability_value(self.target, self.flight) == 0


class GetAllCapabilityValuesTest(TestCase):
    """Tests for get_all_capability_values bulk function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDB.objects.create(db_key="TestTarget")
        cls.movement = CapabilityTypeFactory(name="movement")
        cls.flight = CapabilityTypeFactory(name="flight")

        cls.hasted = ConditionTemplateFactory(name="hasted")
        cls.winged = ConditionTemplateFactory(name="winged")
        cls.slowed = ConditionTemplateFactory(name="slowed")

        ConditionCapabilityEffectFactory(
            condition=cls.hasted,
            capability=cls.movement,
            value=10,
        )
        ConditionCapabilityEffectFactory(
            condition=cls.winged,
            capability=cls.flight,
            value=20,
        )
        ConditionCapabilityEffectFactory(
            condition=cls.slowed,
            capability=cls.movement,
            value=-3,
        )

    def test_empty_when_no_conditions(self):
        """Returns empty dict when character has no conditions."""
        result = get_all_capability_values(self.target)
        assert result == {}

    def test_single_capability(self):
        """Returns single capability from one condition."""
        ConditionInstanceFactory(target=self.target, condition=self.winged)
        result = get_all_capability_values(self.target)
        assert result == {self.flight.id: 20}

    def test_multiple_capabilities(self):
        """Returns all affected capabilities."""
        ConditionInstanceFactory(target=self.target, condition=self.hasted)
        ConditionInstanceFactory(target=self.target, condition=self.winged)
        result = get_all_capability_values(self.target)
        assert result == {self.movement.id: 10, self.flight.id: 20}

    def test_stacking_same_capability(self):
        """Multiple conditions on same capability stack additively."""
        ConditionInstanceFactory(target=self.target, condition=self.hasted)
        ConditionInstanceFactory(target=self.target, condition=self.slowed)
        result = get_all_capability_values(self.target)
        # 10 + (-3) = 7
        assert result == {self.movement.id: 7}

    def test_floor_at_zero(self):
        """Negative totals clamp to 0."""
        ConditionInstanceFactory(target=self.target, condition=self.slowed)
        result = get_all_capability_values(self.target)
        # -3 floored to 0
        assert result == {self.movement.id: 0}


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

        # Stage 1: -25 movement (stage-specific, condition=None)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage1,
            capability=cls.movement,
            value=-25,
        )

        # Stage 2: -50 movement (stage-specific, condition=None)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage2,
            capability=cls.movement,
            value=-50,
        )

        # Stage 3: -100 movement (effectively blocked)
        ConditionCapabilityEffectFactory(
            condition=None,
            stage=cls.stage3,
            capability=cls.movement,
            value=-100,
        )

    def test_stage_1_effect(self):
        """Test effect at stage 1."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage1,
        )

        status = get_capability_status(self.target, self.movement)

        # -25 * 1.0 severity = -25, floored to 0
        assert status.value == 0
        assert status.condition_contributions[0][1] == -25

    def test_stage_2_effect(self):
        """Test effect at stage 2."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage2,
        )

        status = get_capability_status(self.target, self.movement)

        # -50 * 1.5 severity = -75, floored to 0
        assert status.value == 0
        assert status.condition_contributions[0][1] == -75

    def test_stage_3_effect(self):
        """Test effect at stage 3 (effectively blocked)."""
        ConditionInstanceFactory(
            target=self.target,
            condition=self.poison,
            current_stage=self.stage3,
        )

        status = get_capability_status(self.target, self.movement)

        # -100 * 2.0 severity = -200, floored to 0
        assert status.value == 0


class ConditionPercentageModifiersTest(TestCase):
    """Tests for condition percentage modifier service functions."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.models import (
            Distinction,
            DistinctionCategory,
            DistinctionEffect,
        )
        from world.mechanics.models import ModifierCategory, ModifierTarget

        # Create character with sheet
        cls.character_sheet = CharacterSheetFactory()
        cls.target = cls.character_sheet.character

        # Create percentage modifier categories
        cls.control_percent, _ = ModifierCategory.objects.get_or_create(
            name="condition_control_percent",
            defaults={
                "description": "Condition control loss percentage",
                "display_order": 12,
            },
        )
        cls.intensity_percent, _ = ModifierCategory.objects.get_or_create(
            name="condition_intensity_percent",
            defaults={
                "description": "Condition intensity gain percentage",
                "display_order": 13,
            },
        )
        cls.penalty_percent, _ = ModifierCategory.objects.get_or_create(
            name="condition_penalty_percent",
            defaults={
                "description": "Condition penalty percentage",
                "display_order": 14,
            },
        )

        # Create percentage modifier types
        cls.anger_control, _ = ModifierTarget.objects.get_or_create(
            category=cls.control_percent,
            name="anger",
            defaults={"description": "Anger control loss percent"},
        )
        cls.anger_intensity, _ = ModifierTarget.objects.get_or_create(
            category=cls.intensity_percent,
            name="anger",
            defaults={"description": "Anger intensity gain percent"},
        )
        cls.humbled_penalty, _ = ModifierTarget.objects.get_or_create(
            category=cls.penalty_percent,
            name="humbled",
            defaults={"description": "Humbled penalty percent"},
        )

        # Create personality category
        cls.personality_category, _ = DistinctionCategory.objects.get_or_create(
            slug="personality",
            defaults={"name": "Personality", "display_order": 3},
        )

        # Create Wrathful distinction
        cls.wrathful, _ = Distinction.objects.get_or_create(
            slug="wrathful",
            defaults={
                "name": "Wrathful",
                "category": cls.personality_category,
                "cost_per_rank": -5,
                "max_rank": 1,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.wrathful,
            target=cls.anger_control,
            defaults={
                "value_per_rank": 100,
                "description": "+100% anger control loss",
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.wrathful,
            target=cls.anger_intensity,
            defaults={
                "value_per_rank": 50,
                "description": "+50% anger intensity gain",
            },
        )

        # Create Hubris distinction
        cls.hubris, _ = Distinction.objects.get_or_create(
            slug="hubris",
            defaults={
                "name": "Hubris",
                "category": cls.personality_category,
                "cost_per_rank": -5,
                "max_rank": 1,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.hubris,
            target=cls.humbled_penalty,
            defaults={
                "value_per_rank": 100,
                "description": "+100% humbled penalties",
            },
        )

    def test_no_modifier_without_distinction(self):
        """Test zero modifier when character has no relevant distinctions."""
        from world.conditions.services import (
            get_condition_control_percent_modifier,
            get_condition_intensity_percent_modifier,
            get_condition_penalty_percent_modifier,
        )

        control = get_condition_control_percent_modifier(self.target, "anger")
        intensity = get_condition_intensity_percent_modifier(self.target, "anger")
        penalty = get_condition_penalty_percent_modifier(self.target, "humbled")

        assert control == 0
        assert intensity == 0
        assert penalty == 0

    def test_wrathful_anger_control_modifier(self):
        """Test Wrathful grants +100% anger control loss modifier."""
        from world.conditions.services import get_condition_control_percent_modifier
        from world.distinctions.models import CharacterDistinction
        from world.mechanics.services import create_distinction_modifiers

        # Grant Wrathful distinction
        char_distinction = CharacterDistinction.objects.create(
            character=self.target,
            distinction=self.wrathful,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        modifier = get_condition_control_percent_modifier(self.target, "anger")

        assert modifier == 100

    def test_wrathful_anger_intensity_modifier(self):
        """Test Wrathful grants +50% anger intensity gain modifier."""
        from world.conditions.services import get_condition_intensity_percent_modifier
        from world.distinctions.models import CharacterDistinction
        from world.mechanics.services import create_distinction_modifiers

        # Grant Wrathful distinction
        char_distinction = CharacterDistinction.objects.create(
            character=self.target,
            distinction=self.wrathful,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        modifier = get_condition_intensity_percent_modifier(self.target, "anger")

        assert modifier == 50

    def test_hubris_humbled_penalty_modifier(self):
        """Test Hubris grants +100% humbled penalty modifier."""
        from world.conditions.services import get_condition_penalty_percent_modifier
        from world.distinctions.models import CharacterDistinction
        from world.mechanics.services import create_distinction_modifiers

        # Grant Hubris distinction
        char_distinction = CharacterDistinction.objects.create(
            character=self.target,
            distinction=self.hubris,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        modifier = get_condition_penalty_percent_modifier(self.target, "humbled")

        assert modifier == 100

    def test_modifier_case_insensitive(self):
        """Test condition name matching is case-insensitive."""
        from world.conditions.services import get_condition_control_percent_modifier
        from world.distinctions.models import CharacterDistinction
        from world.mechanics.services import create_distinction_modifiers

        char_distinction = CharacterDistinction.objects.create(
            character=self.target,
            distinction=self.wrathful,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Should match regardless of case
        assert get_condition_control_percent_modifier(self.target, "ANGER") == 100
        assert get_condition_control_percent_modifier(self.target, "Anger") == 100

    def test_modifiers_stack_from_multiple_sources(self):
        """Test that percentage modifiers from multiple sources stack."""
        from world.conditions.services import get_condition_control_percent_modifier
        from world.distinctions.models import (
            CharacterDistinction,
            Distinction,
            DistinctionEffect,
        )
        from world.mechanics.services import create_distinction_modifiers

        # Create another distinction with anger control modifier
        other, _ = Distinction.objects.get_or_create(
            slug="other-anger-distinction",
            defaults={
                "name": "Other Anger",
                "category": self.personality_category,
                "cost_per_rank": 5,
                "max_rank": 1,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=other,
            target=self.anger_control,
            defaults={
                "value_per_rank": 25,
                "description": "+25% anger control loss",
            },
        )

        # Grant both distinctions
        wrathful_cd = CharacterDistinction.objects.create(
            character=self.target,
            distinction=self.wrathful,
            rank=1,
        )
        create_distinction_modifiers(wrathful_cd)

        other_cd = CharacterDistinction.objects.create(
            character=self.target,
            distinction=other,
            rank=1,
        )
        create_distinction_modifiers(other_cd)

        modifier = get_condition_control_percent_modifier(self.target, "anger")

        assert modifier == 125  # 100 + 25


class AdvanceConditionSeverityTests(TestCase):
    """Tests for severity-driven stage advancement."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory()
        cls.template = ConditionTemplateFactory(
            has_progression=True,
            is_stackable=False,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.template,
            stage_order=1,
            name="Strain",
            severity_threshold=1,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.template,
            stage_order=2,
            name="Fracture",
            severity_threshold=10,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.template,
            stage_order=3,
            name="Collapse",
            severity_threshold=25,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )

    def test_advance_within_stage(self) -> None:
        """Severity increases without crossing threshold — stage unchanged."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_result = advance_condition_severity(instance, 5)
        instance.refresh_from_db()
        assert instance.severity == 6
        assert instance.current_stage == self.stage1
        assert not advance_result.stage_changed
        assert advance_result.total_severity == 6

    def test_advance_crosses_threshold(self) -> None:
        """Severity crossing threshold advances to next stage."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_result = advance_condition_severity(instance, 12)
        instance.refresh_from_db()
        assert instance.severity == 13
        assert instance.current_stage == self.stage2
        assert advance_result.stage_changed
        assert advance_result.previous_stage == self.stage1
        assert advance_result.new_stage == self.stage2

    def test_advance_skips_stages(self) -> None:
        """Large severity jump can skip intermediate stages."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_result = advance_condition_severity(instance, 30)
        instance.refresh_from_db()
        assert instance.severity == 31
        assert instance.current_stage == self.stage3
        assert advance_result.stage_changed
        assert advance_result.previous_stage == self.stage1
        assert advance_result.new_stage == self.stage3

    def test_advance_at_final_stage(self) -> None:
        """Severity keeps accumulating past final stage without error."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_condition_severity(instance, 30)  # reach stage3
        advance_result = advance_condition_severity(instance, 50)
        instance.refresh_from_db()
        assert instance.severity == 81
        assert instance.current_stage == self.stage3
        assert not advance_result.stage_changed

    def test_advance_no_severity_threshold_stages_ignored(self) -> None:
        """Stages without severity_threshold are not considered."""
        template = ConditionTemplateFactory(has_progression=True, is_stackable=False)
        ConditionStageFactory(
            condition=template,
            stage_order=1,
            name="S1",
            severity_threshold=1,
            rounds_to_next=None,
        )
        ConditionStageFactory(
            condition=template,
            stage_order=2,
            name="Time-Only",
            severity_threshold=None,
            rounds_to_next=5,
        )
        s3 = ConditionStageFactory(
            condition=template,
            stage_order=3,
            name="S3",
            severity_threshold=25,
            rounds_to_next=None,
        )
        result = apply_condition(self.character, template)
        instance = result.instance
        advance_condition_severity(instance, 30)
        instance.refresh_from_db()
        assert instance.current_stage == s3


class BuildBulkContextTest(TestCase):
    """Tests for _build_bulk_context batch-fetch function."""

    @classmethod
    def setUpTestData(cls):
        cls.target = CharacterFactory(db_key="bulk_target")
        cls.template = ConditionTemplateFactory()
        cls.existing = ConditionInstanceFactory(
            target=cls.target,
            condition=cls.template,
        )

    def test_context_contains_active_instances(self):
        ctx = _build_bulk_context([self.target], [self.template])
        instances = ctx.active_instances_by_target.get(self.target.pk, [])
        assert len(instances) == 1
        assert instances[0].condition_id == self.template.pk

    def test_context_contains_existing_pair(self):
        ctx = _build_bulk_context([self.target], [self.template])
        existing = ctx.get_existing_instance(self.target.pk, self.template.pk)
        assert existing is not None
        assert existing.pk == self.existing.pk

    def test_context_empty_for_unknown_target(self):
        other = CharacterFactory(db_key="other")
        ctx = _build_bulk_context([other], [self.template])
        instances = ctx.active_instances_by_target.get(other.pk, [])
        assert len(instances) == 0

    def test_context_fetches_prevention_interactions(self):
        blocker = ConditionTemplateFactory(name="blocker")
        ConditionConditionInteractionFactory(
            condition=self.template,
            other_condition=blocker,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )
        ctx = _build_bulk_context([self.target], [blocker])
        assert len(ctx.prevention_interactions) >= 1

    def test_context_fetches_first_stages(self):
        progressive = ConditionTemplateFactory(name="staged", has_progression=True)
        stage1 = ConditionStageFactory(condition=progressive, stage_order=1, rounds_to_next=2)
        ConditionStageFactory(condition=progressive, stage_order=2, rounds_to_next=None)

        ctx = _build_bulk_context([self.target], [progressive])
        assert ctx.first_stages.get(progressive.pk) == stage1


class BulkApplyConditionsTest(TestCase):
    """Tests for bulk_apply_conditions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.target1 = CharacterFactory(db_key="bulk_t1")
        cls.target2 = CharacterFactory(db_key="bulk_t2")
        cls.template1 = ConditionTemplateFactory(name="Burn")
        cls.template2 = ConditionTemplateFactory(name="Poison")

    def test_applies_to_multiple_targets(self):
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target2, self.template1)],
        )
        assert len(results) == 2
        assert all(r.success for r in results)
        assert ConditionInstance.objects.filter(condition=self.template1).count() == 2

    def test_applies_multiple_conditions_to_one_target(self):
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target1, self.template2)],
        )
        assert len(results) == 2
        assert all(r.success for r in results)
        assert ConditionInstance.objects.filter(target=self.target1).count() == 2

    def test_prevention_still_works(self):
        blocker = ConditionTemplateFactory(name="Blocker")
        ConditionInstanceFactory(target=self.target1, condition=blocker)
        ConditionConditionInteractionFactory(
            condition=blocker,
            other_condition=self.template2,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target1, self.template2)],
        )
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].was_prevented is True

    def test_empty_list_returns_empty(self):
        results = bulk_apply_conditions([])
        assert results == []

    def test_severity_and_source_passed_through(self):
        source = CharacterFactory(db_key="caster")
        results = bulk_apply_conditions(
            [(self.target1, self.template1)],
            severity=3,
            source_character=source,
            source_description="spell hit",
        )
        assert results[0].success is True
        inst = results[0].instance
        assert inst.severity == 3
        assert inst.source_character == source
        assert inst.source_description == "spell hit"

    def test_interaction_removal_visible_to_subsequent_iterations(self):
        """C1 regression: if applying A removes condition X via interaction,
        applying B in the same batch should not see X as active."""

        existing_cond = ConditionTemplateFactory(name="ExistingCond")
        ConditionInstanceFactory(target=self.target1, condition=existing_cond)

        # template1 removes existing_cond on application
        ConditionConditionInteractionFactory(
            condition=self.template1,
            other_condition=existing_cond,
            trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_OTHER,
        )

        # existing_cond would prevent template2 — but it should be gone
        ConditionConditionInteractionFactory(
            condition=existing_cond,
            other_condition=self.template2,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )

        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target1, self.template2)],
        )
        # template1 succeeds and removes existing_cond
        assert results[0].success is True
        assert existing_cond in results[0].removed_conditions
        # template2 should NOT be prevented (existing_cond was removed)
        assert results[1].success is True

    def test_duplicate_pair_stacks_instead_of_creating_duplicate(self):
        """C2 regression: same (target, template) twice should stack/refresh,
        not create two separate instances."""

        stackable = ConditionTemplateFactory(
            name="Stackable",
            is_stackable=True,
            max_stacks=5,
        )
        results = bulk_apply_conditions(
            [(self.target1, stackable), (self.target1, stackable)],
        )
        assert results[0].success is True
        assert results[1].success is True
        # Should be one instance with 2 stacks, not two instances
        assert (
            ConditionInstance.objects.filter(
                target=self.target1,
                condition=stackable,
            ).count()
            == 1
        )
        instance = ConditionInstance.objects.get(
            target=self.target1,
            condition=stackable,
        )
        assert instance.stacks == 2

    def test_suppressed_conditions_ignored_in_bulk(self):
        """C3 regression: suppressed conditions should not participate
        in prevention checks during bulk application."""

        blocker = ConditionTemplateFactory(name="SuppressedBlocker")
        ConditionInstanceFactory(
            target=self.target1,
            condition=blocker,
            is_suppressed=True,
        )
        ConditionConditionInteractionFactory(
            condition=blocker,
            other_condition=self.template1,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )

        results = bulk_apply_conditions(
            [(self.target1, self.template1)],
        )
        # Should NOT be prevented — blocker is suppressed
        assert results[0].success is True

    def test_removed_condition_not_resurrected_by_later_apply(self):
        """M1 regression: if interaction removes B, and B is also being
        applied later in the batch, it should create a fresh instance
        rather than .save() on the deleted one."""
        wet = ConditionTemplateFactory(name="Wet")
        burning = ConditionTemplateFactory(name="Burning")

        # target1 already has burning
        ConditionInstanceFactory(target=self.target1, condition=burning)

        # wet removes burning on application
        ConditionConditionInteractionFactory(
            condition=wet,
            other_condition=burning,
            trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_OTHER,
        )

        results = bulk_apply_conditions(
            [(self.target1, wet), (self.target1, burning)],
        )
        # wet succeeds and removes existing burning
        assert results[0].success is True
        assert burning in results[0].removed_conditions
        # burning re-applied as a fresh instance (not the deleted one)
        assert results[1].success is True
        assert results[1].instance is not None
        assert (
            ConditionInstance.objects.filter(
                target=self.target1,
                condition=burning,
            ).count()
            == 1
        )

    def test_intra_batch_interaction_detected(self):
        """M2 regression: if both A and B are new in the batch, and A
        has an interaction with B, it should be detected."""
        fire = ConditionTemplateFactory(name="FireNew")
        ice = ConditionTemplateFactory(name="IceNew")

        # fire removes ice on application (self-applied trigger)
        ConditionConditionInteractionFactory(
            condition=ice,
            other_condition=fire,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_SELF,
        )

        # Apply ice first, then fire — fire should trigger ice removal
        results = bulk_apply_conditions(
            [(self.target1, ice), (self.target1, fire)],
        )
        assert results[0].success is True  # ice applied
        assert results[1].success is True  # fire applied, removes ice
        assert ice in results[1].removed_conditions
        # Only fire should remain
        remaining = ConditionInstance.objects.filter(target=self.target1)
        assert remaining.count() == 1
        assert remaining.first().condition == fire
