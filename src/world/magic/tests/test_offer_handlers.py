"""Unit tests for offer handler path-resolution logic (#1344).

The path-resolution helper (_resolve_path_by_name) has three fiddly branches
(zero match, ambiguous match, auto-select when name omitted) that the E2E test
doesn't reach. These focused tests cover them.
"""

from __future__ import annotations

from django.test import TestCase

from commands.exceptions import CommandError
from world.classes.factories import PathFactory
from world.classes.models import PathStage


def _make_paths(*names: str):
    return [PathFactory(name=n, stage=PathStage.PUISSANT) for n in names]


class TestResolvePathByName(TestCase):
    def test_exact_match(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        result = _resolve_path_by_name("Ironwood", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_case_insensitive_substring(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        result = _resolve_path_by_name("iron", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_zero_matches_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("Ember", paths)

    def test_ambiguous_match_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood Peak", "Ironwood Vale")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("Ironwood", paths)

    def test_auto_select_single_path_when_name_omitted(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood")
        result = _resolve_path_by_name("", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_no_name_multiple_paths_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("", paths)
