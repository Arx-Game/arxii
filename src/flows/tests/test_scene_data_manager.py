"""
Tests for flows.scene_data_manager module.
"""

from unittest.mock import Mock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from flows.flow_event import FlowEvent
from flows.scene_data_manager import SceneDataManager


class TestSceneDataManager(TestCase):
    """Tests for SceneDataManager class."""

    def setUp(self):
        """Set up test data."""
        self.manager = SceneDataManager()

        # Create mock state for testing
        self.mock_state = Mock()
        self.mock_state.test_attr = "initial_value"
        self.mock_state.test_list = ["item1", "item2"]
        self.mock_state.test_dict = {"key1": "value1", "key2": "value2"}

    def test_init_creates_empty_containers(self):
        """Test that initialization creates empty containers."""
        manager = SceneDataManager()

        assert manager.states == {}
        assert manager.flow_events == {}
        assert manager.trigger_history == {}

    def test_reset_clears_containers(self):
        """Test that reset clears all stored data."""
        # Add some data
        self.manager.states[1] = Mock()
        self.manager.flow_events["test"] = Mock()
        self.manager.trigger_history[(1, (1, 2))] = 3

        self.manager.reset()

        assert self.manager.states == {}
        assert self.manager.flow_events == {}
        # Note: reset() doesn't clear trigger_history, only states and flow_events

    def test_set_context_value_existing_state(self):
        """Test setting an attribute on an existing state."""
        # Store a state first
        self.manager.states[1] = self.mock_state

        result = self.manager.set_context_value(1, "test_attr", "new_value")

        assert result == self.mock_state
        assert self.mock_state.test_attr == "new_value"

    def test_set_context_value_missing_state(self):
        """Test setting an attribute when state doesn't exist."""
        result = self.manager.set_context_value(999, "test_attr", "new_value")

        assert result is None

    def test_get_context_value_existing_state_and_attribute(self):
        """Test getting an attribute from an existing state."""
        self.manager.states[1] = self.mock_state

        result = self.manager.get_context_value(1, "test_attr")

        assert result == "initial_value"

    def test_get_context_value_existing_state_missing_attribute(self):
        """Test getting a missing attribute from an existing state."""
        # Use a simpler object to avoid Mock complexity
        simple_state = type("SimpleState", (), {"test_attr": "value"})()
        self.manager.states[1] = simple_state

        result = self.manager.get_context_value(1, "nonexistent_attr")
        assert result is None

    def test_get_context_value_missing_state(self):
        """Test getting an attribute when state doesn't exist."""
        result = self.manager.get_context_value(999, "test_attr")

        assert result is None

    def test_modify_context_value_success(self):
        """Test modifying an attribute with a callable."""
        self.manager.states[1] = self.mock_state

        def add_suffix(value):
            return f"{value}_modified"

        result = self.manager.modify_context_value(1, "test_attr", add_suffix)

        assert result == self.mock_state
        assert self.mock_state.test_attr == "initial_value_modified"

    def test_modify_context_value_missing_attribute(self):
        """Test modifying a missing attribute (should receive None)."""
        simple_state = type("SimpleState", (), {"test_attr": "value"})()
        self.manager.states[1] = simple_state

        def handle_none(value):
            return "default_value" if value is None else f"{value}_modified"

        result = self.manager.modify_context_value(1, "missing_attr", handle_none)

        assert result == simple_state
        assert simple_state.missing_attr == "default_value"

    def test_modify_context_value_missing_state(self):
        """Test modifying when state doesn't exist."""

        def modifier(value):
            return "modified"

        result = self.manager.modify_context_value(999, "test_attr", modifier)

        assert result is None

    def test_add_to_context_list_new_item(self):
        """Test adding a new item to a list attribute."""
        self.manager.states[1] = self.mock_state

        result = self.manager.add_to_context_list(1, "test_list", "item3")

        assert result == self.mock_state
        assert "item3" in self.mock_state.test_list
        assert len(self.mock_state.test_list) == 3

    def test_add_to_context_list_existing_item(self):
        """Test adding an existing item to a list (should not duplicate)."""
        self.manager.states[1] = self.mock_state

        result = self.manager.add_to_context_list(1, "test_list", "item1")

        assert result == self.mock_state
        # Should not duplicate existing item
        assert self.mock_state.test_list.count("item1") == 1

    def test_add_to_context_list_missing_attribute(self):
        """Test adding to a missing list attribute (should create new list)."""
        simple_state = type("SimpleState", (), {"test_list": ["item1", "item2"]})()
        self.manager.states[1] = simple_state

        result = self.manager.add_to_context_list(1, "new_list", "item1")

        assert result == simple_state
        assert simple_state.new_list == ["item1"]

    def test_remove_from_context_list_existing_item(self):
        """Test removing an existing item from a list."""
        self.manager.states[1] = self.mock_state

        result = self.manager.remove_from_context_list(1, "test_list", "item1")

        assert result == self.mock_state
        assert "item1" not in self.mock_state.test_list
        assert len(self.mock_state.test_list) == 1

    def test_remove_from_context_list_missing_item(self):
        """Test removing a non-existent item from a list (should not error)."""
        self.manager.states[1] = self.mock_state
        original_list = list(self.mock_state.test_list)

        result = self.manager.remove_from_context_list(1, "test_list", "nonexistent")

        assert result == self.mock_state
        assert self.mock_state.test_list == original_list

    def test_set_context_dict_value(self):
        """Test setting a key in a dict attribute."""
        self.manager.states[1] = self.mock_state

        result = self.manager.set_context_dict_value(1, "test_dict", "key3", "value3")

        assert result == self.mock_state
        assert self.mock_state.test_dict["key3"] == "value3"

    def test_set_context_dict_value_existing_key(self):
        """Test overwriting an existing key in a dict attribute."""
        self.manager.states[1] = self.mock_state

        result = self.manager.set_context_dict_value(
            1, "test_dict", "key1", "new_value"
        )

        assert result == self.mock_state
        assert self.mock_state.test_dict["key1"] == "new_value"

    def test_set_context_dict_value_missing_attribute(self):
        """Test setting a key in a missing dict attribute (should create new dict)."""
        simple_state = type(
            "SimpleState", (), {"test_dict": {"key1": "value1", "key2": "value2"}}
        )()
        self.manager.states[1] = simple_state

        result = self.manager.set_context_dict_value(1, "new_dict", "key1", "value1")

        assert result == simple_state
        assert simple_state.new_dict == {"key1": "value1"}

    def test_remove_context_dict_value_existing_key(self):
        """Test removing an existing key from a dict attribute."""
        self.manager.states[1] = self.mock_state

        result = self.manager.remove_context_dict_value(1, "test_dict", "key1")

        assert result == self.mock_state
        assert "key1" not in self.mock_state.test_dict
        assert "key2" in self.mock_state.test_dict

    def test_remove_context_dict_value_missing_key(self):
        """Test removing a non-existent key from a dict (should not error)."""
        self.manager.states[1] = self.mock_state
        original_dict = dict(self.mock_state.test_dict)

        result = self.manager.remove_context_dict_value(1, "test_dict", "nonexistent")

        assert result == self.mock_state
        assert self.mock_state.test_dict == original_dict

    def test_modify_context_dict_value_existing_key(self):
        """Test modifying an existing key in a dict attribute."""
        self.manager.states[1] = self.mock_state

        def add_suffix(value):
            return f"{value}_modified"

        result = self.manager.modify_context_dict_value(
            1, "test_dict", "key1", add_suffix
        )

        assert result == self.mock_state
        assert self.mock_state.test_dict["key1"] == "value1_modified"

    def test_modify_context_dict_value_missing_key(self):
        """Test modifying a missing key in a dict (should receive None)."""
        self.manager.states[1] = self.mock_state

        def handle_none(value):
            return "default" if value is None else f"{value}_modified"

        result = self.manager.modify_context_dict_value(
            1, "test_dict", "new_key", handle_none
        )

        assert result == self.mock_state
        assert self.mock_state.test_dict["new_key"] == "default"

    def test_store_flow_event(self):
        """Test storing a FlowEvent."""
        event = FlowEvent("test_event", {})

        self.manager.store_flow_event("test_key", event)

        assert self.manager.flow_events["test_key"] == event

    def test_get_state_by_pk_cached(self):
        """Test getting a state that's already cached."""
        self.manager.states[1] = self.mock_state

        result = self.manager.get_state_by_pk(1)

        assert result == self.mock_state

    @patch("evennia.objects.models.ObjectDB.objects.get")
    def test_get_state_by_pk_not_cached_success(self, mock_get):
        """Test getting a state that's not cached but object exists."""
        mock_obj = Mock()
        mock_obj.pk = 1
        mock_get.return_value = mock_obj

        with patch.object(self.manager, "initialize_state_for_object") as mock_init:
            mock_init.return_value = self.mock_state

            result = self.manager.get_state_by_pk(1)

            assert result == self.mock_state
            mock_get.assert_called_once_with(pk=1)
            mock_init.assert_called_once_with(mock_obj)

    @patch("evennia.objects.models.ObjectDB.objects.get")
    def test_get_state_by_pk_object_not_found(self, mock_get):
        """Test getting a state when object doesn't exist."""
        mock_get.side_effect = ObjectDB.DoesNotExist()

        result = self.manager.get_state_by_pk(999)

        assert result is None

    @patch("evennia.objects.models.ObjectDB.objects.get")
    def test_get_state_by_pk_invalid_pk(self, mock_get):
        """Test getting a state with invalid pk."""
        # Test with non-numeric pk
        result = self.manager.get_state_by_pk("not_a_number")
        assert result is None

        # Test with None
        result = self.manager.get_state_by_pk(None)
        assert result is None

    @patch("behaviors.models.BehaviorPackageInstance.objects.select_related")
    def test_initialize_state_for_object(self, mock_select_related):
        """Test initializing state for an Evennia object."""
        mock_obj = Mock()
        mock_obj.pk = 1
        mock_obj.get_object_state.return_value = self.mock_state

        mock_packages = [Mock(), Mock()]
        mock_select_related.return_value.filter.return_value = mock_packages

        result = self.manager.initialize_state_for_object(mock_obj)

        assert result == self.mock_state
        assert self.manager.states[1] == self.mock_state
        assert self.mock_state.packages == mock_packages
        self.mock_state.initialize_state.assert_called_once()

    def test_has_trigger_fired_true(self):
        """Test checking if a trigger has fired (true case)."""
        self.manager.trigger_history[(1, (2, 3))] = 1

        result = self.manager.has_trigger_fired(1, (2, 3))

        assert result is True

    def test_has_trigger_fired_false(self):
        """Test checking if a trigger has fired (false case)."""
        result = self.manager.has_trigger_fired(1, (2, 3))

        assert result is False

    def test_mark_trigger_fired_new(self):
        """Test marking a trigger as fired for the first time."""
        self.manager.mark_trigger_fired(1, (2, 3))

        assert self.manager.trigger_history[(1, (2, 3))] == 1

    def test_mark_trigger_fired_existing(self):
        """Test marking a trigger as fired when it already has a count."""
        self.manager.trigger_history[(1, (2, 3))] = 2

        self.manager.mark_trigger_fired(1, (2, 3))

        assert self.manager.trigger_history[(1, (2, 3))] == 3

    def test_get_trigger_fire_count_existing(self):
        """Test getting fire count for an existing trigger."""
        self.manager.trigger_history[(1, (2, 3))] = 5

        result = self.manager.get_trigger_fire_count(1, (2, 3))

        assert result == 5

    def test_get_trigger_fire_count_missing(self):
        """Test getting fire count for a non-existent trigger."""
        result = self.manager.get_trigger_fire_count(1, (2, 3))

        assert result == 0

    def test_trigger_methods_with_none_values(self):
        """Test trigger methods with None values in event_key tuple."""
        event_key = (None, 5)

        self.manager.mark_trigger_fired(1, event_key)

        assert self.manager.has_trigger_fired(1, event_key) is True
        assert self.manager.get_trigger_fire_count(1, event_key) == 1
