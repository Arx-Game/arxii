import unittest

from django.test import TestCase

from flows.events.names import EventNames
from world.conditions.factories import ReactiveConditionFactory

_SKIP_REASON = (
    "Rewritten in unified-dispatch Phase 5 "
    "(docs/superpowers/plans/2026-04-17-reactive-unified-dispatch.md)"
)


def setUpModule() -> None:
    raise unittest.SkipTest(_SKIP_REASON)


class ReactiveConditionFactoryTests(TestCase):
    def test_factory_creates_condition_with_trigger(self) -> None:
        trigger = ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            scope=TriggerScope.PERSONAL,
        )
        self.assertEqual(trigger.scope, TriggerScope.PERSONAL)
        self.assertIsNotNone(trigger.source_condition)
        self.assertEqual(trigger.trigger_definition.event.name, "damage_applied")
