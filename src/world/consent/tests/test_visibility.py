"""Tests for VisibilityMixin behavior.

The VisibilityMixin is abstract and requires a concrete model to test fully.
Full integration tests are in codex/tests/test_visibility.py using
CodexTeachingOffer which implements the mixin.

These tests verify the mixin structure and enum values.
"""

from django.test import TestCase

from world.consent.models import VisibilityMixin


class VisibilityMixinTests(TestCase):
    """Tests for VisibilityMixin structure."""

    def test_visibility_mode_public(self):
        """PUBLIC mode has correct value."""
        assert VisibilityMixin.VisibilityMode.PUBLIC == "public"

    def test_visibility_mode_private(self):
        """PRIVATE mode has correct value."""
        assert VisibilityMixin.VisibilityMode.PRIVATE == "private"

    def test_visibility_mode_characters(self):
        """CHARACTERS mode has correct value."""
        assert VisibilityMixin.VisibilityMode.CHARACTERS == "characters"

    def test_visibility_mode_groups(self):
        """GROUPS mode has correct value."""
        assert VisibilityMixin.VisibilityMode.GROUPS == "groups"

    def test_visibility_mode_choices(self):
        """VisibilityMixin has all expected mode choices."""
        choices = dict(VisibilityMixin.VisibilityMode.choices)
        assert len(choices) == 4
        assert "public" in choices
        assert "private" in choices
        assert "characters" in choices
        assert "groups" in choices

    def test_default_visibility_mode(self):
        """Default visibility mode is PRIVATE."""
        # Check the field definition
        field = VisibilityMixin._meta.get_field("visibility_mode")
        assert field.default == VisibilityMixin.VisibilityMode.PRIVATE
