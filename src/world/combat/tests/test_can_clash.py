"""Tests for the ``can_clash`` Property-overlap predicate (Phase 3)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.clash import can_clash


class CanClashTests(TestCase):
    """Pure-Python set-overlap predicate. No DB calls."""

    def test_empty_a_returns_false(self) -> None:
        self.assertFalse(can_clash(frozenset(), frozenset({1, 2})))

    def test_empty_b_returns_false(self) -> None:
        self.assertFalse(can_clash(frozenset({1, 2}), frozenset()))

    def test_both_empty_returns_false(self) -> None:
        self.assertFalse(can_clash(frozenset(), frozenset()))

    def test_no_overlap_returns_false(self) -> None:
        self.assertFalse(can_clash(frozenset({1, 2}), frozenset({3, 4})))

    def test_single_overlap_returns_true(self) -> None:
        self.assertTrue(can_clash(frozenset({1, 2}), frozenset({2, 3})))

    def test_multiple_overlap_returns_true(self) -> None:
        self.assertTrue(can_clash(frozenset({1, 2, 3}), frozenset({2, 3, 4})))

    def test_identical_sets_return_true(self) -> None:
        self.assertTrue(can_clash(frozenset({1, 2}), frozenset({1, 2})))

    def test_symmetric(self) -> None:
        a = frozenset({1, 2})
        b = frozenset({2, 3})
        self.assertEqual(can_clash(a, b), can_clash(b, a))

    def test_accepts_set_type(self) -> None:
        # The function signature allows ``set[int]`` too.
        self.assertTrue(can_clash({1, 2}, {2, 3}))
