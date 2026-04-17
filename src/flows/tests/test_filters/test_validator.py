"""Tests for filter DSL schema validator."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from flows.filters.validator import validate_filter_schema


class FilterValidatorTests(TestCase):
    """Test save-time filter schema validation."""

    def test_known_path_ok(self) -> None:
        """Valid path to payload field should not raise."""
        # damage_pre_apply payload has fields: target, amount, damage_type, source
        f = {"path": "damage_type", "op": "==", "value": "fire"}
        validate_filter_schema(f, event_name="damage_pre_apply")

    def test_unknown_path_raises(self) -> None:
        """Path with unknown field should raise ValidationError."""
        f = {"path": "nonexistent_field", "op": "==", "value": "x"}
        with self.assertRaises(ValidationError):
            validate_filter_schema(f, event_name="damage_pre_apply")

    def test_unknown_event_raises(self) -> None:
        """Unknown event name should raise ValidationError."""
        f = {"path": "x", "op": "==", "value": "y"}
        with self.assertRaises(ValidationError):
            validate_filter_schema(f, event_name="not_a_real_event")

    def test_nested_and_validates_children(self) -> None:
        """Invalid path in nested and clause should raise."""
        f = {
            "and": [
                {"path": "damage_type", "op": "==", "value": "fire"},
                {"path": "bogus_field", "op": "==", "value": "x"},
            ]
        }
        with self.assertRaises(ValidationError):
            validate_filter_schema(f, event_name="damage_pre_apply")

    def test_self_paths_not_validated(self) -> None:
        """self.* paths refer to handler owner, not payload; skipped."""
        f = {"path": "self.covenant", "op": "==", "value": "iron"}
        validate_filter_schema(f, event_name="damage_pre_apply")
