"""Tests for the live trigger dispatch path (_trigger_should_fire) (#2531).

Verifies that _trigger_should_fire evaluates both base_filter_condition
(from the TriggerDefinition) and additional_filter_condition (from the Trigger
instance) with AND semantics, using evaluate_filter() (the live DSL).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from flows.emit import _trigger_should_fire
from flows.factories import TriggerDefinitionFactory, TriggerFactory


class TriggerShouldFireTests(TestCase):
    """_trigger_should_fire evaluates base + additional filters with AND semantics."""

    def _make_trigger(self, *, base=None, additional=None, event_name="test_event"):
        """Create a trigger with the given base/additional filters."""
        trigger_def = TriggerDefinitionFactory(
            event_name=event_name,
            base_filter_condition=base,
        )
        return TriggerFactory(
            trigger_definition=trigger_def,
            additional_filter_condition=additional,
        )

    def test_no_filters_passes(self):
        """A trigger with no base and no additional filter fires (pass-through)."""
        trigger = self._make_trigger(base=None, additional=None)
        self.assertTrue(_trigger_should_fire(trigger, SimpleNamespace(), "test_event"))

    def test_base_filter_must_pass(self):
        """A trigger whose base filter doesn't match the payload does not fire."""
        trigger = self._make_trigger(
            base={"path": "type", "op": "==", "value": "fire"},
        )
        # Payload with wrong type — base filter fails.
        self.assertFalse(_trigger_should_fire(trigger, SimpleNamespace(type="cold"), "test_event"))
        # Payload with matching type — base filter passes.
        self.assertTrue(_trigger_should_fire(trigger, SimpleNamespace(type="fire"), "test_event"))

    def test_additional_filter_must_pass(self):
        """A trigger whose additional filter doesn't match the payload does not fire."""
        trigger = self._make_trigger(
            base=None,
            additional={"path": "amount", "op": ">", "value": 5},
        )
        self.assertFalse(_trigger_should_fire(trigger, SimpleNamespace(amount=3), "test_event"))
        self.assertTrue(_trigger_should_fire(trigger, SimpleNamespace(amount=10), "test_event"))

    def test_both_filters_must_pass_and_semantics(self):
        """Both base and additional must pass (AND semantics)."""
        trigger = self._make_trigger(
            base={"path": "type", "op": "==", "value": "fire"},
            additional={"path": "amount", "op": ">", "value": 5},
        )
        # Both pass.
        self.assertTrue(
            _trigger_should_fire(trigger, SimpleNamespace(type="fire", amount=10), "test_event")
        )
        # Base fails.
        self.assertFalse(
            _trigger_should_fire(trigger, SimpleNamespace(type="cold", amount=10), "test_event")
        )
        # Additional fails.
        self.assertFalse(
            _trigger_should_fire(trigger, SimpleNamespace(type="fire", amount=3), "test_event")
        )
        # Both fail.
        self.assertFalse(
            _trigger_should_fire(trigger, SimpleNamespace(type="cold", amount=3), "test_event")
        )

    def test_base_only_no_additional_soul_tether_pattern(self):
        """The soul tether pattern: base filter set, no additional — fires when base matches."""
        trigger = self._make_trigger(
            base={"path": "type", "op": "==", "value": "corruption"},
        )
        # No additional_filter_condition — only the base filter is evaluated.
        self.assertTrue(
            _trigger_should_fire(trigger, SimpleNamespace(type="corruption"), "test_event")
        )
        self.assertFalse(
            _trigger_should_fire(trigger, SimpleNamespace(type="healing"), "test_event")
        )
