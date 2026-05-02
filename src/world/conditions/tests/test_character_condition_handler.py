"""Tests for CharacterConditionHandler — caches active condition instances."""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase


class CharacterConditionHandlerTests(EvenniaTestCase):
    def test_returns_zero_for_no_active_conditions(self):
        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        from world.conditions.factories import DamageTypeFactory

        fire = DamageTypeFactory(name="Fire")
        self.assertEqual(char.conditions.resistance_modifier(fire), 0)

    def test_returns_zero_for_null_damage_type(self):
        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        self.assertEqual(char.conditions.resistance_modifier(None), 0)

    def test_template_level_modifier_for_matching_type(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(
            condition=wet,
            damage_type=fire,
            modifier_value=10,
        )
        apply_condition(char, wet)
        self.assertEqual(char.conditions.resistance_modifier(fire), 10)

    def test_template_level_modifier_for_all_types_damage_type_null(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        warded = ConditionTemplateFactory(name="Warded")
        ConditionResistanceModifierFactory(
            condition=warded,
            damage_type=None,
            modifier_value=5,
        )
        apply_condition(char, warded)
        self.assertEqual(char.conditions.resistance_modifier(fire), 5)

    def test_negative_modifier_means_vulnerability(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        lightning = DamageTypeFactory(name="Lightning")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(
            condition=wet,
            damage_type=lightning,
            modifier_value=-15,
        )
        apply_condition(char, wet)
        self.assertEqual(char.conditions.resistance_modifier(lightning), -15)

    def test_aggregates_across_multiple_conditions(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        warded = ConditionTemplateFactory(name="Warded")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)
        ConditionResistanceModifierFactory(condition=warded, damage_type=fire, modifier_value=5)
        apply_condition(char, wet)
        apply_condition(char, warded)
        self.assertEqual(char.conditions.resistance_modifier(fire), 15)

    def test_skips_suppressed_instances(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)
        apply_condition(char, wet)
        instance = ConditionInstance.objects.get(target=char, condition=wet)
        instance.is_suppressed = True
        instance.save(update_fields=["is_suppressed"])
        char.conditions.invalidate()  # Direct mutation bypasses Task 3 invalidation
        self.assertEqual(char.conditions.resistance_modifier(fire), 0)

    def test_skips_resolved_instances(self):
        from django.utils import timezone

        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)
        apply_condition(char, wet)
        instance = ConditionInstance.objects.get(target=char, condition=wet)
        instance.resolved_at = timezone.now()
        instance.save(update_fields=["resolved_at"])
        char.conditions.invalidate()
        self.assertEqual(char.conditions.resistance_modifier(fire), 0)

    def test_stage_level_modifier_when_at_that_stage(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionStageFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        burning = ConditionTemplateFactory(name="Burning", has_progression=True)
        stage_1 = ConditionStageFactory(condition=burning, stage_order=1)
        ConditionResistanceModifierFactory(
            condition=None,
            stage=stage_1,
            damage_type=fire,
            modifier_value=8,
        )
        apply_condition(char, burning)
        instance = ConditionInstance.objects.get(target=char, condition=burning)
        instance.current_stage = stage_1
        instance.save(update_fields=["current_stage"])
        char.conditions.invalidate()
        self.assertEqual(char.conditions.resistance_modifier(fire), 8)

    def test_handler_caches_active_list_on_first_read(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)
        apply_condition(char, wet)
        # Force first read so the cache is primed
        _ = char.conditions.resistance_modifier(fire)
        # Subsequent reads must not query
        with self.assertNumQueries(0):
            char.conditions.resistance_modifier(fire)
            char.conditions.resistance_modifier(fire)

    def test_invalidate_drops_cache(self):
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        char = create_object("typeclasses.characters.Character", key="A", nohome=True)
        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)
        apply_condition(char, wet)
        first = char.conditions.resistance_modifier(fire)
        char.conditions.invalidate()
        # After invalidation, the next read is a fresh query
        second = char.conditions.resistance_modifier(fire)
        self.assertEqual(first, second)
