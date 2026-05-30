"""Tests for ConditionTemplate.get_by_name cached lookup.

Pins the contract:
- First call queries by name and caches the PK.
- Subsequent calls hit SharedMemoryModel's identity map (zero queries).
- Cache survives within a test; the project's TimedEvenniaTestRunner clears
  it between tests so test rollback can't leak a stale PK.
- DoesNotExist raised when no row matches.
- A stale PK (e.g., production-side deletion that bypassed the cache) is
  detected via DoesNotExist on the by-PK fetch and the cache repopulates.
"""

from __future__ import annotations

from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionTemplate


class GetByNameTests(TestCase):
    def test_returns_matching_template_by_name(self) -> None:
        template = ConditionTemplateFactory(name="Sample Cached Condition")
        result = ConditionTemplate.get_by_name("Sample Cached Condition")
        assert result == template

    def test_raises_does_not_exist_for_missing_name(self) -> None:
        with self.assertRaises(ConditionTemplate.DoesNotExist):
            ConditionTemplate.get_by_name("no-such-template")

    def test_second_call_returns_same_object_no_query(self) -> None:
        ConditionTemplateFactory(name="Cached Twice")
        ConditionTemplate.get_by_name("Cached Twice")  # priming call
        # After priming, the second call should not issue any SQL — the cache
        # provides the PK and SharedMemoryModel's identity map returns the
        # cached Python object directly.
        with self.assertNumQueries(0):
            result = ConditionTemplate.get_by_name("Cached Twice")
        assert result.name == "Cached Twice"

    def test_stale_pk_recovers_via_does_not_exist(self) -> None:
        """If the cached PK no longer exists (e.g., admin-deleted row), the cache
        drops the stale entry and refetches by name."""
        template = ConditionTemplateFactory(name="Will Be Refound")
        # Poison the cache: name maps to a PK that doesn't exist.
        ConditionTemplate._name_pk_cache["Will Be Refound"] = 999_999
        result = ConditionTemplate.get_by_name("Will Be Refound")
        assert result == template
        # Cache is now repaired.
        assert ConditionTemplate._name_pk_cache["Will Be Refound"] == template.pk

    def test_cache_isolated_across_tests(self) -> None:
        """Companion to the test below — together they verify the test-runner
        flush actually clears the name cache between tests."""
        ConditionTemplateFactory(name="Isolation Test Marker")
        ConditionTemplate.get_by_name("Isolation Test Marker")
        assert "Isolation Test Marker" in ConditionTemplate._name_pk_cache

    def test_cache_starts_empty_in_each_test(self) -> None:
        """The previous test populated the cache; this one should start clean
        thanks to the test-runner flush."""
        assert "Isolation Test Marker" not in ConditionTemplate._name_pk_cache
