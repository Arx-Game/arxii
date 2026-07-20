"""Tests for apply_condition's reactive-trigger install + stat-increment integration."""

from django.test import TestCase

from flows.constants import EventName
from flows.factories import FlowDefinitionFactory, TriggerDefinitionFactory
from flows.models.triggers import Trigger
from world.achievements.constants import ConditionEventType
from world.achievements.factories import ConditionStatRuleFactory, StatDefinitionFactory
from world.achievements.models import StatTracker
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition


class ApplyConditionInstallsTriggersTests(TestCase):
    def test_reactive_triggers_get_installed_on_apply(self):
        condition = ConditionTemplateFactory(name="T10 marker A")
        flow = FlowDefinitionFactory(name="T10 flow A")
        trigger_def = TriggerDefinitionFactory(
            name="T10 td A",
            event_name=EventName.TECHNIQUE_CAST,
            flow_definition=flow,
        )
        condition.reactive_triggers.add(trigger_def)
        sheet = CharacterSheetFactory()

        result = apply_condition(target=sheet.character, condition=condition)

        self.assertTrue(result.success)
        installed = Trigger.objects.filter(obj=sheet.character)
        self.assertEqual(installed.count(), 1)
        trigger = installed.first()
        self.assertEqual(trigger.trigger_definition, trigger_def)
        self.assertEqual(trigger.source_condition, result.instance)

    def test_no_triggers_installed_when_template_has_none(self):
        condition = ConditionTemplateFactory(name="T10 marker B")
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        self.assertEqual(Trigger.objects.filter(obj=sheet.character).count(), 0)

    def test_multiple_triggers_installed(self):
        condition = ConditionTemplateFactory(name="T10 marker C")
        flow = FlowDefinitionFactory(name="T10 flow C")
        td1 = TriggerDefinitionFactory(
            name="T10 td C1",
            event_name=EventName.TECHNIQUE_CAST,
            flow_definition=flow,
        )
        td2 = TriggerDefinitionFactory(
            name="T10 td C2",
            event_name=EventName.MOVED,
            flow_definition=flow,
        )
        condition.reactive_triggers.add(td1, td2)
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        self.assertEqual(Trigger.objects.filter(obj=sheet.character).count(), 2)

    def test_base_filter_condition_available_via_trigger_definition(self):
        """_install_reactive_side_effects creates Triggers whose base_filter_condition
        is accessible via trigger_definition — emit_event evaluates it directly
        (#2531: two-stage base + additional filter evaluation, no copy needed)."""
        condition = ConditionTemplateFactory(name="T10 filter copy test")
        flow = FlowDefinitionFactory(name="T10 filter copy flow")
        filter_cond = {"path": "target", "op": "==", "value": "self"}
        trigger_def = TriggerDefinitionFactory(
            name="T10 filter copy td",
            event_name=EventName.TECHNIQUE_CAST,
            flow_definition=flow,
            base_filter_condition=filter_cond,
        )
        condition.reactive_triggers.add(trigger_def)
        sheet = CharacterSheetFactory()

        result = apply_condition(target=sheet.character, condition=condition)

        self.assertTrue(result.success)
        trigger = Trigger.objects.get(obj=sheet.character, trigger_definition=trigger_def)
        # The base filter lives on the definition, not copied to additional_filter_condition.
        self.assertEqual(
            trigger.trigger_definition.base_filter_condition,
            filter_cond,
            "base_filter_condition must be set on the TriggerDefinition",
        )
        self.assertIsNone(
            trigger.additional_filter_condition,
            "additional_filter_condition should be None when no per-instance filter is set"
            " (#2531: base filter is read from the definition, not copied)",
        )


class ApplyConditionIncrementsBridgedStatsTests(TestCase):
    def test_stat_rule_fires_on_gained(self):
        condition = ConditionTemplateFactory(name="T10 stat A")
        stat = StatDefinitionFactory(key="conditions.t10.stat_a.gained")
        ConditionStatRuleFactory(
            stat=stat,
            condition=condition,
            event_type=ConditionEventType.GAINED,
            increment_amount=1,
        )
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        tracker = StatTracker.objects.get(character_sheet=sheet, stat=stat)
        self.assertEqual(tracker.value, 1)

    def test_stat_rule_does_not_fire_when_rule_absent(self):
        condition = ConditionTemplateFactory(name="T10 stat B")
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        self.assertEqual(StatTracker.objects.filter(character_sheet=sheet).count(), 0)

    def test_increment_amount_is_honored(self):
        condition = ConditionTemplateFactory(name="T10 stat C")
        stat = StatDefinitionFactory(key="conditions.t10.stat_c.gained")
        ConditionStatRuleFactory(
            stat=stat,
            condition=condition,
            event_type=ConditionEventType.GAINED,
            increment_amount=3,
        )
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        tracker = StatTracker.objects.get(character_sheet=sheet, stat=stat)
        self.assertEqual(tracker.value, 3)

    def test_multiple_stat_rules_all_fire(self):
        condition = ConditionTemplateFactory(name="T10 stat D")
        stat1 = StatDefinitionFactory(key="conditions.t10.stat_d1.gained")
        stat2 = StatDefinitionFactory(key="conditions.t10.stat_d2.gained")
        ConditionStatRuleFactory(
            stat=stat1,
            condition=condition,
            event_type=ConditionEventType.GAINED,
        )
        ConditionStatRuleFactory(
            stat=stat2,
            condition=condition,
            event_type=ConditionEventType.GAINED,
        )
        sheet = CharacterSheetFactory()

        apply_condition(target=sheet.character, condition=condition)

        self.assertEqual(
            StatTracker.objects.get(character_sheet=sheet, stat=stat1).value,
            1,
        )
        self.assertEqual(
            StatTracker.objects.get(character_sheet=sheet, stat=stat2).value,
            1,
        )
