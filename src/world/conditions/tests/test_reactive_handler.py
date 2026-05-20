"""Tests for ConditionTemplateReactiveHandler."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from flows.factories import TriggerDefinitionFactory
from world.achievements.constants import ConditionEventType
from world.achievements.factories import ConditionStatRuleFactory, StatDefinitionFactory
from world.conditions.factories import ConditionTemplateFactory


class ConditionTemplateReactiveHandlerTests(TestCase):
    def test_reactive_trigger_definitions_returns_list(self):
        template = ConditionTemplateFactory()
        td1 = TriggerDefinitionFactory(name="T8 td1")
        td2 = TriggerDefinitionFactory(name="T8 td2")
        template.reactive_triggers.add(td1, td2)

        triggers = template.reactive_handler.reactive_trigger_definitions

        self.assertEqual(len(triggers), 2)
        self.assertIn(td1, triggers)
        self.assertIn(td2, triggers)

    def test_reactive_trigger_definitions_empty_when_none_attached(self):
        template = ConditionTemplateFactory()
        self.assertEqual(template.reactive_handler.reactive_trigger_definitions, [])

    def test_stat_rules_for_event_returns_matching_rules(self):
        template = ConditionTemplateFactory()
        stat_a = StatDefinitionFactory(key="conditions.t8.a.gained")
        stat_b = StatDefinitionFactory(key="conditions.t8.b.gained")
        ConditionStatRuleFactory(
            condition=template,
            stat=stat_a,
            event_type=ConditionEventType.GAINED,
        )
        ConditionStatRuleFactory(
            condition=template,
            stat=stat_b,
            event_type=ConditionEventType.GAINED,
        )

        rules = template.reactive_handler.stat_rules_for_event(ConditionEventType.GAINED)

        self.assertEqual(len(rules), 2)
        self.assertEqual({r.stat for r in rules}, {stat_a, stat_b})

    def test_stat_rules_for_event_empty_when_no_rules(self):
        template = ConditionTemplateFactory()
        self.assertEqual(
            template.reactive_handler.stat_rules_for_event(ConditionEventType.GAINED),
            [],
        )

    def test_cached_property_returns_same_instance(self):
        template = ConditionTemplateFactory()
        h1 = template.reactive_handler
        h2 = template.reactive_handler
        self.assertIs(h1, h2)

    def test_warm_path_makes_no_queries(self):
        template = ConditionTemplateFactory()
        td = TriggerDefinitionFactory(name="T8 warm td")
        template.reactive_triggers.add(td)
        stat = StatDefinitionFactory(key="conditions.t8.warm.gained")
        ConditionStatRuleFactory(
            condition=template,
            stat=stat,
            event_type=ConditionEventType.GAINED,
        )

        # Warm the cache
        handler = template.reactive_handler
        _ = handler.reactive_trigger_definitions
        _ = handler.stat_rules_for_event(ConditionEventType.GAINED)

        # Second access should be zero queries.
        with CaptureQueriesContext(connection) as ctx:
            _ = handler.reactive_trigger_definitions
            _ = handler.stat_rules_for_event(ConditionEventType.GAINED)
        self.assertEqual(
            len(ctx),
            0,
            f"Warm path made queries: {[q['sql'] for q in ctx.captured_queries]}",
        )
