from django.core.exceptions import ValidationError
from django.test import TestCase

from flows.constants import EventName
from flows.factories import TriggerDefinitionFactory, TriggerFactory


class TriggerFilterValidationTests(TestCase):
    def test_trigger_definition_unknown_path_rejected(self) -> None:
        """TriggerDefinition.clean() rejects filter with unknown path."""
        trigger_def = TriggerDefinitionFactory.create(
            event_name=EventName.DAMAGE_APPLIED,
            base_filter_condition={"path": "bogus", "op": "==", "value": 1},
        )
        with self.assertRaises(ValidationError) as cm:
            trigger_def.full_clean()
        self.assertIn("bogus", str(cm.exception))

    def test_trigger_definition_known_path_accepted(self) -> None:
        """TriggerDefinition.clean() accepts filter with known path."""
        trigger_def = TriggerDefinitionFactory.create(
            event_name=EventName.DAMAGE_APPLIED,
            base_filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
        )
        trigger_def.full_clean()  # should not raise

    def test_trigger_definition_empty_condition_accepted(self) -> None:
        """TriggerDefinition.clean() accepts empty filter."""
        trigger_def = TriggerDefinitionFactory.create(
            event_name=EventName.DAMAGE_APPLIED,
            base_filter_condition={},
        )
        trigger_def.full_clean()  # should not raise

    def test_trigger_unknown_path_rejected(self) -> None:
        """Trigger.clean() rejects filter with unknown path."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={"path": "bogus", "op": "==", "value": 1},
        )
        with self.assertRaises(ValidationError) as cm:
            trigger.full_clean()
        self.assertIn("bogus", str(cm.exception))

    def test_trigger_known_path_accepted(self) -> None:
        """Trigger.clean() accepts filter with known path."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
        )
        trigger.full_clean()  # should not raise

    def test_trigger_empty_condition_accepted(self) -> None:
        """Trigger.clean() accepts empty filter."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={},
        )
        trigger.full_clean()  # should not raise

    def test_trigger_self_path_skipped(self) -> None:
        """Trigger.clean() skips validation of self.* paths."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={"path": "self.unknown_attr", "op": "==", "value": 1},
        )
        trigger.full_clean()  # should not raise, self.* paths are skipped

    def test_trigger_nested_filter_with_and(self) -> None:
        """Trigger.clean() validates nested filters with 'and' operator."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={
                "and": [
                    {"path": "damage_type", "op": "==", "value": "fire"},
                    {"path": "amount_dealt", "op": ">", "value": 5},
                ]
            },
        )
        trigger.full_clean()  # should not raise

    def test_trigger_nested_filter_with_bad_path(self) -> None:
        """Trigger.clean() rejects nested filter with unknown path."""
        trigger_def = TriggerDefinitionFactory(event_name=EventName.DAMAGE_APPLIED)
        trigger = TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition={
                "and": [
                    {"path": "damage_type", "op": "==", "value": "fire"},
                    {"path": "unknown_field", "op": ">", "value": 5},
                ]
            },
        )
        with self.assertRaises(ValidationError) as cm:
            trigger.full_clean()
        self.assertIn("unknown_field", str(cm.exception))
