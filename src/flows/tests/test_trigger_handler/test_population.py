from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from flows.constants import EventName
from flows.trigger_handler import TriggerHandler
from world.conditions.factories import ReactiveConditionFactory


class TriggerHandlerPopulationTests(TestCase):
    def test_populates_on_first_access(self) -> None:
        # Attach two reactive triggers to the same character via
        # ReactiveConditionFactory.
        t1 = ReactiveConditionFactory(event_name=EventName.DAMAGE_APPLIED)
        character = t1.obj  # Trigger.obj is the ObjectDB owner
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_LANDED,
            target=character,
        )

        handler = TriggerHandler(owner=character)

        with CaptureQueriesContext(connection) as first:
            _ = handler.triggers_for("damage_applied")
        self.assertGreater(len(first), 0, "First access MUST populate via a query")

        with CaptureQueriesContext(connection) as second:
            _ = handler.triggers_for("damage_applied")
        self.assertEqual(
            len(second),
            0,
            f"Second access must not re-query; saw: {[q['sql'] for q in second.captured_queries]}",
        )
