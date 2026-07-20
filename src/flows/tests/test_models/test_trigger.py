from django.test import TestCase

from flows.factories import (
    SceneDataManagerFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)


class TestTrigger(TestCase):
    """Test suite for the Trigger model."""

    def setUp(self):
        self.context = SceneDataManagerFactory()
        self.trigger_def = TriggerDefinitionFactory(
            event_name="test_event",
            base_filter_condition={"foo": "bar"},
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
            assert isinstance(data, dict)

        with self.assertNumQueries(0):
            # Second access uses cache
            data_again = self.trigger.data_map
            assert data_again == data


class TestSystemInstalledTrigger(TestCase):
    """A Trigger with no source_condition (system-installed) is valid and fires."""

    def setUp(self):
        from flows.trigger_handler import TriggerHandler

        self.handler = TriggerHandler(owner=None)

    def test_trigger_without_source_condition_saves(self):
        td = TriggerDefinitionFactory(event_name="test_event")
        trigger = TriggerFactory(trigger_definition=td, source_condition=None)
        self.assertIsNone(trigger.source_condition)

    def test_system_installed_trigger_is_active(self):
        """_is_active returns True for a trigger with no source_condition."""
        from unittest.mock import MagicMock

        trigger = MagicMock()
        trigger.source_stage = None
        trigger.source_condition = None
        self.assertTrue(self.handler._is_active(trigger))

    def test_source_stage_set_source_condition_none_does_not_raise(self):
        """_is_active does not raise when source_stage is set but source_condition is None."""
        from unittest.mock import MagicMock

        trigger = MagicMock()
        trigger.source_stage = MagicMock()  # non-None stage
        trigger.source_condition = None
        # Must not raise; the guard should return True (system-installed triggers are always active)
        result = self.handler._is_active(trigger)
        self.assertTrue(result)
