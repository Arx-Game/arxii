from django.test import TestCase

from flows.constants import TriggerScope
from flows.events.names import EventNames
from world.conditions.factories import ReactiveConditionFactory


class ReactiveConditionFactoryTests(TestCase):
    def test_factory_creates_condition_with_trigger(self) -> None:
        trigger = ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            scope=TriggerScope.PERSONAL,
        )
        self.assertEqual(trigger.scope, TriggerScope.PERSONAL)
        self.assertIsNotNone(trigger.source_condition)
        self.assertEqual(trigger.trigger_definition.event.name, "damage_applied")
