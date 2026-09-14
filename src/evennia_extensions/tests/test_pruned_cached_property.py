"""Tests for PrunedCachedProperty in isolation, no Django models needed for most cases."""

from django.utils.functional import cached_property
from evennia.utils.test_resources import EvenniaTest

from evennia_extensions.cached_property import PrunedCachedProperty


class _FakeRow:
    """A stand-in for a model instance with just a `pk` attribute."""

    def __init__(self, pk):
        self.pk = pk


class _Holder:
    calls = 0

    @PrunedCachedProperty
    def rows(self):
        _Holder.calls += 1
        return [_FakeRow(1), _FakeRow(2), _FakeRow(3)]


class PrunedCachedPropertyTests(EvenniaTest):
    def setUp(self):
        super().setUp()
        _Holder.calls = 0

    def test_computes_once(self):
        holder = _Holder()
        first = holder.rows
        second = holder.rows
        self.assertEqual(_Holder.calls, 1)
        self.assertIs(first, second)

    def test_filters_pk_nulled_row_on_later_read_without_requerying(self):
        holder = _Holder()
        rows = holder.rows
        rows[1].pk = None  # simulate a Collector.delete() zombie
        filtered = holder.rows
        self.assertEqual([r.pk for r in filtered], [1, 3])
        self.assertEqual(_Holder.calls, 1, "must not re-query, only re-filter")

    def test_is_instance_of_django_cached_property(self):
        self.assertIsInstance(_Holder.__dict__["rows"], cached_property)

    def test_full_reassignment_still_works(self):
        holder = _Holder()
        _ = holder.rows  # populate
        holder.rows = [_FakeRow(9)]
        self.assertEqual([r.pk for r in holder.rows], [9])
        self.assertEqual(_Holder.calls, 1, "reassignment must not trigger a recompute")

    def test_append_mutates_in_place_without_set(self):
        holder = _Holder()
        rows = holder.rows
        rows.append(_FakeRow(4))
        self.assertEqual([r.pk for r in holder.rows], [1, 2, 3, 4])
