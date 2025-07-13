from unittest.mock import MagicMock

from django.test import TestCase

from flows.factories import FlowEventFactory, TriggerDefinitionFactory


class TestTriggerDefinition(TestCase):
    def test_matches_event_type(self):
        """Test that event type must match the trigger definition's event key."""
        tdef = TriggerDefinitionFactory(event__key="test_event")

        matching_event = FlowEventFactory.create(event_type="test_event")
        non_matching_event = FlowEventFactory.create(event_type="wrong_event")

        self.assertTrue(tdef.matches_event(matching_event))
        self.assertFalse(tdef.matches_event(non_matching_event))

    def test_matches_event_with_conditions(self):
        """Test that conditions are checked when present."""
        tdef = TriggerDefinitionFactory(
            event__key="test_event", base_filter_condition={"foo": "bar"}
        )

        event = FlowEventFactory.create(event_type="test_event")
        event.source.context = MagicMock()

        # Test with passing condition
        event.source.context.get_variable.return_value = "bar"
        self.assertTrue(tdef.matches_event(event))
        event.source.context.get_variable.assert_called_once_with("foo")

        # Test with failing condition
        event.source.context.get_variable.return_value = "wrong"
        self.assertFalse(tdef.matches_event(event))

    def test_matches_event_with_missing_variable(self):
        """Test that missing variables in context cause match to fail."""
        tdef = TriggerDefinitionFactory(
            event__key="test_event", base_filter_condition={"missing": "value"}
        )

        event = FlowEventFactory.create(event_type="test_event")
        event.source.context = MagicMock()
        event.source.context.get_variable.side_effect = KeyError("missing")

        self.assertFalse(tdef.matches_event(event))
