from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.factories import (
    ContextDataFactory,
    FlowEventFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.flow_event import FlowEvent
from flows.models import Trigger


class TestTrigger(TestCase):
    """Test suite for the Trigger model."""

    def setUp(self):
        self.context = ContextDataFactory()
        self.trigger_def = TriggerDefinitionFactory(
            event__key="test_event", base_filter_condition={"foo": "bar"}
        )
        self.trigger = TriggerFactory(
            trigger_definition=self.trigger_def,
            additional_filter_condition={"baz": "qux"},
        )

    def test_data_map_caches_queryset(self):
        """Test that data_map caches the queryset results."""
        with self.assertNumQueries(1):
            # First access hits the database
            data = self.trigger.data_map
            self.assertIsInstance(data, dict)

        with self.assertNumQueries(0):
            # Second access uses cache
            data_again = self.trigger.data_map
            self.assertEqual(data_again, data)

    def test_should_trigger_for_event_checks_definition_match(self):
        """Test that the trigger checks its definition's match first."""
        event = FlowEventFactory(event_type="test_event")

        with patch.object(
            self.trigger.trigger_definition, "matches_event"
        ) as mock_matches:
            mock_matches.return_value = False
            self.assertFalse(self.trigger.should_trigger_for_event(event))
            mock_matches.assert_called_once_with(event)

    def test_should_trigger_for_event_checks_additional_conditions(self):
        """Test that additional filter conditions are checked."""
        event = FlowEventFactory(event_type="test_event")

        with patch.object(
            self.trigger.trigger_definition, "matches_event", return_value=True
        ):
            # Mock the private _check_conditions method
            with patch.object(
                Trigger, "_check_conditions", return_value=True
            ) as mock_check:
                self.assertTrue(self.trigger.should_trigger_for_event(event))
                mock_check.assert_called_once_with(
                    self.trigger.additional_filter_condition, event.context
                )

    def test_should_trigger_for_event_checks_conditions(self):
        """Test that the trigger checks conditions against event data."""
        # Create a mock source for the event
        source = MagicMock()
        source.context = MagicMock()

        # Test with no conditions
        event = FlowEvent(
            "test_event", source=source, data={"foo": "bar", "baz": "qux"}
        )
        with patch.object(
            self.trigger.trigger_definition, "matches_event", return_value=True
        ):
            self.trigger.additional_filter_condition = {}
            self.assertTrue(self.trigger.should_trigger_for_event(event))

        # Test with passing conditions
        event = FlowEvent(
            "test_event", source=source, data={"foo": "bar", "baz": "qux"}
        )
        with patch.object(
            self.trigger.trigger_definition, "matches_event", return_value=True
        ):
            self.trigger.additional_filter_condition = {"baz": "qux"}
            self.assertTrue(self.trigger.should_trigger_for_event(event))

        # Test with failing conditions
        event = FlowEvent(
            "test_event", source=source, data={"foo": "bar", "baz": "wrong"}
        )
        with patch.object(
            self.trigger.trigger_definition, "matches_event", return_value=True
        ):
            self.trigger.additional_filter_condition = {"baz": "qux"}
            self.assertFalse(self.trigger.should_trigger_for_event(event))

        # Test with missing data
        event = FlowEvent("test_event", source=source, data={"foo": "bar"})
        with patch.object(
            self.trigger.trigger_definition, "matches_event", return_value=True
        ):
            self.trigger.additional_filter_condition = {"missing": "value"}
            self.assertFalse(self.trigger.should_trigger_for_event(event))
