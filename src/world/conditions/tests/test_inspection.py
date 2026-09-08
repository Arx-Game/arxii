"""Condition authoring diagnostics (#3715)."""

from django.test import TestCase

from flows.factories import TriggerDefinitionFactory
from world.conditions.constants import ConditionInteractionOutcome, ConditionInteractionTrigger
from world.conditions.factories import (
    ConditionCapabilityEffectFactory,
    ConditionCategoryFactory,
    ConditionConditionInteractionFactory,
    ConditionDamageInteractionFactory,
    ConditionDamageOverTimeFactory,
    ConditionModifierEffectFactory,
    ConditionResistanceModifierFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
    TreatmentTemplateFactory,
)
from world.conditions.inspection import (
    ConditionMechanicsState,
    condition_template_prefetches,
    inspect_condition_template,
)
from world.mechanics.factories import PropertyFactory


class ConditionMechanicsInspectionTests(TestCase):
    def test_empty_condition_requires_manual_verification(self):
        template = ConditionTemplateFactory(
            category=ConditionCategoryFactory(is_negative=False),
            name="Uncatalogued condition",
        )

        diagnostic = inspect_condition_template(template)

        self.assertTrue(diagnostic.referenced)
        self.assertEqual(diagnostic.state, ConditionMechanicsState.MANUAL_VERIFICATION)
        self.assertTrue(diagnostic.requires_manual_verification)
        self.assertEqual(diagnostic.channels, ())
        self.assertIn("requires manual verification", diagnostic.as_text())
        self.assertNotIn("inert", diagnostic.as_text())

    def test_negative_category_alone_is_not_a_mechanical_channel(self):
        template = ConditionTemplateFactory(name="Negative label only")

        diagnostic = inspect_condition_template(template)

        self.assertEqual(diagnostic.state, ConditionMechanicsState.MANUAL_VERIFICATION)
        self.assertEqual(diagnostic.channels, ())

    def test_behavior_category_is_recognized_without_modifier_rows(self):
        template = ConditionTemplateFactory(
            category=ConditionCategoryFactory(alters_behavior=True, is_negative=False),
            name="Charmed shape",
        )

        diagnostic = inspect_condition_template(template)

        self.assertEqual(diagnostic.state, ConditionMechanicsState.WIRED)
        self.assertIn("category.alters_behavior", diagnostic.channels)

    def test_all_delivery_channels_are_inspected(self):
        template = ConditionTemplateFactory(
            category=ConditionCategoryFactory(
                alters_behavior=True,
                grants_intangibility=True,
                conceals_from_perception=True,
                is_negative=False,
            ),
            affects_turn_order=True,
            draws_aggro=True,
            break_free_mode="periodic",
            exploitable_tiers=1,
            upkeep_anima_per_round=1,
            reactive_anima_cost=1,
            is_clash_lock=True,
            passive_decay_per_day=1,
        )
        ConditionCapabilityEffectFactory(condition=template)
        ConditionModifierEffectFactory(condition=template)
        ConditionDamageOverTimeFactory(condition=template)
        ConditionResistanceModifierFactory(condition=template, damage_type=DamageTypeFactory())
        template.properties.add(PropertyFactory())
        template.reactive_triggers.add(TriggerDefinitionFactory())
        ConditionDamageInteractionFactory(condition=template, damage_type=DamageTypeFactory())
        other = ConditionTemplateFactory(category=ConditionCategoryFactory(is_negative=False))
        ConditionConditionInteractionFactory(
            condition=template,
            other_condition=other,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_SELF,
        )
        stage = ConditionStageFactory(condition=template)
        stage.properties.add(PropertyFactory())
        stage.on_entry_conditions.add(other)
        TreatmentTemplateFactory(target_condition=template)

        diagnostic = inspect_condition_template(template)

        expected = {
            "capability_effect",
            "modifier_effect",
            "resistance_modifier",
            "damage_over_time",
            "category.alters_behavior",
            "category.grants_intangibility",
            "category.conceals_from_perception",
            "combat.affects_turn_order",
            "combat.draws_aggro",
            "combat.break_free",
            "combat.exploitable_tiers",
            "combat.upkeep_anima",
            "combat.reactive_anima",
            "combat.passive_decay",
            "combat.clash_lock",
            "property",
            "reactive_trigger",
            "stage",
            "stage_entry",
            "damage_interaction",
            "condition_interaction",
            "treatment_target",
        }
        self.assertTrue(expected.issubset(set(diagnostic.channels)))

    def test_prefetches_make_inspection_query_free(self):
        template = ConditionTemplateFactory(
            category=ConditionCategoryFactory(is_negative=False),
        )
        loaded = (
            ConditionTemplateFactory._meta.model.objects.select_related("category")
            .prefetch_related(*condition_template_prefetches())
            .get(pk=template.pk)
        )

        with self.assertNumQueries(0):
            diagnostic = inspect_condition_template(loaded)

        self.assertEqual(diagnostic.state, ConditionMechanicsState.MANUAL_VERIFICATION)
