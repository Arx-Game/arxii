from django.test import TestCase

from flows.factories import FlowEventFactory


class FlowEventMatchesConditionsTests(TestCase):
    """Tests for FlowEvent.matches_conditions."""

    def test_matching_conditions_returns_true(self):
        event = FlowEventFactory(data={"foo": "bar", "baz": 1})
        self.assertTrue(event.matches_conditions({"foo": "bar", "baz": 1}))

    def test_non_matching_conditions_returns_false(self):
        event = FlowEventFactory(data={"foo": "bar", "baz": 1})
        self.assertFalse(event.matches_conditions({"foo": "baz"}))
        self.assertFalse(event.matches_conditions({"foo": "bar", "baz": 2}))

    def test_missing_keys_handled_gracefully(self):
        event = FlowEventFactory(data={"foo": "bar"})
        self.assertFalse(event.matches_conditions({"missing": "value"}))
