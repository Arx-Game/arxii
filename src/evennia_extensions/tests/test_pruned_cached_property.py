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
        # Django's own to_attr freshness check is
        # isinstance(getattr(model, to_attr, None), cached_property), which
        # routes through __get__(None, cls) — reading the class __dict__
        # directly would bypass the descriptor protocol entirely and could
        # pass even if __get__'s `if instance is None` branch were broken.
        self.assertIsInstance(_Holder.rows, cached_property)

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

    def test_delete_clears_cache_and_next_read_recomputes(self):
        holder = _Holder()
        _ = holder.rows  # populate
        del holder.rows
        _ = holder.rows
        self.assertEqual(_Holder.calls, 2, "del must invalidate so the next read recomputes")

    def test_dict_freshness_contract_for_to_attr_detection(self):
        # This is exactly what Django's is_to_attr_fetched checks to decide
        # whether a Prefetch(..., to_attr=...) needs to run: a fresh instance
        # must not have the attr in __dict__ yet, and one read must populate it.
        holder = _Holder()
        self.assertNotIn("rows", holder.__dict__)
        _ = holder.rows
        self.assertIn("rows", holder.__dict__)

    def test_recomputes_after_cache_popped_like_related_cache_fields_would(self):
        # Mirrors what clear_django_cached_properties()/related_cache_fields
        # does on a write elsewhere: pop the instance __dict__ entry directly.
        holder = _Holder()
        _ = holder.rows
        holder.__dict__.pop("rows", None)
        _ = holder.rows
        self.assertEqual(_Holder.calls, 2, "popping the cache must force a recompute")
