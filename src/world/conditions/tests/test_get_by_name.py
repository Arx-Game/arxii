"""Tests for ConditionTemplate.get_by_name cached lookup.

Pins the contract:
- First call queries by name and warms the natural-key index (#2687).
- Subsequent calls hit SharedMemoryModel's identity map (zero queries).
- The index survives within a test; the project's TimedEvenniaTestRunner clears
  it between tests so test rollback can't leak a stale PK.
- DoesNotExist raised when no row matches.
- A stale PK (e.g., production-side deletion that bypassed the index) is
  detected via DoesNotExist on the by-PK fetch and the index re-warms.
"""

from __future__ import annotations

from django.test import TestCase

from core.natural_keys import natural_key_index
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
        # After priming, the second call should not issue any SQL — the index
        # provides the PK and SharedMemoryModel's identity map returns the
        # cached Python object directly.
        with self.assertNumQueries(0):
            result = ConditionTemplate.get_by_name("Cached Twice")
        assert result.name == "Cached Twice"

    def test_condition_template_is_a_lookup_table(self) -> None:
        """The whole (small, hot-path) catalog loads once — a second lookup of a
        DIFFERENT name costs nothing."""
        ConditionTemplateFactory(name="Warm Alpha")
        ConditionTemplateFactory(name="Warm Beta")
        ConditionTemplate.get_by_name("Warm Alpha")  # warms the table
        with self.assertNumQueries(0):
            assert ConditionTemplate.get_by_name("warm beta").name == "Warm Beta"

    def test_stale_pk_recovers_via_does_not_exist(self) -> None:
        """A poisoned index entry (e.g. admin-deleted row) is detected on the
        by-pk fetch; the lookup table re-warms and resolves correctly."""
        template = ConditionTemplateFactory(name="Will Be Refound")
        ConditionTemplate.get_by_name("Will Be Refound")  # warms
        natural_key_index(ConditionTemplate)[("will be refound",)] = 999_999
        result = ConditionTemplate.get_by_name("Will Be Refound")
        assert result == template
        assert natural_key_index(ConditionTemplate)[("will be refound",)] == template.pk

    def test_cache_isolated_across_tests(self) -> None:
        """Companion to the test below — together they verify the test-runner
        flush actually clears the natural-key index between tests."""
        ConditionTemplateFactory(name="Isolation Test Marker")
        ConditionTemplate.get_by_name("Isolation Test Marker")
        assert ("isolation test marker",) in natural_key_index(ConditionTemplate)

    def test_cache_starts_empty_in_each_test(self) -> None:
        """The previous test populated the index; this one should start clean."""
        assert ("isolation test marker",) not in natural_key_index(ConditionTemplate)
