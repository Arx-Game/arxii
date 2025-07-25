from django.test import TestCase

from flows.factories import FlowEventFactory, TriggerDefinitionFactory


class TestTriggerDefinition(TestCase):
    def test_matches_event_type(self):
        """Test that event type must match the trigger definition's event key."""
        tdef = TriggerDefinitionFactory(event__name="test_event")

        matching_event = FlowEventFactory.create(event_type="test_event")
        non_matching_event = FlowEventFactory.create(event_type="wrong_event")

        self.assertTrue(tdef.matches_event(matching_event))
        self.assertFalse(tdef.matches_event(non_matching_event))

    def test_matches_event_with_conditions(self):
        """Test that conditions are checked when present."""
        tdef = TriggerDefinitionFactory(
            event__name="test_event", base_filter_condition={"foo": "bar"}
        )

        # Event with data matching the condition
        event = FlowEventFactory(event_type="test_event", data={"foo": "bar"})
        self.assertTrue(tdef.matches_event(event))

        # Event with data not matching the condition
        event_wrong = FlowEventFactory(event_type="test_event", data={"foo": "wrong"})
        self.assertFalse(tdef.matches_event(event_wrong))

    def test_matches_event_with_missing_variable(self):
        """Test that missing variables in context cause match to fail."""
        tdef = TriggerDefinitionFactory(
            event__name="test_event", base_filter_condition={"missing": "value"}
        )

        # Event missing the required condition key should fail
        event = FlowEventFactory(event_type="test_event", data={})
        self.assertFalse(tdef.matches_event(event))
