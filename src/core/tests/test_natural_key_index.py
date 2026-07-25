"""Tests for the natural-key → pk index in core.natural_keys (#2687)."""

from __future__ import annotations

from django.test import TestCase

from core.natural_keys import (
    _NK_WARMED,
    _index_key,
    flush_natural_key_indexes,
    index_owner,
    natural_key_index,
)
from world.species.models import Species


class IndexKeyNormalizationTests(TestCase):
    """_index_key() makes keys hashable and caseless."""

    def test_casefolds_string_components(self) -> None:
        assert _index_key(("Fire Bolt",)) == ("fire bolt",)
        assert _index_key(("FIRE BOLT",)) == ("fire bolt",)

    def test_leaves_non_string_components_alone(self) -> None:
        assert _index_key(("Rank", 30, None)) == ("rank", 30, None)

    def test_converts_nested_lists_to_tuples(self) -> None:
        # Self-referential FK natural keys arrive as nested lists.
        assert _index_key(("Mammals", ["Creatures", None])) == (
            "mammals",
            ("creatures", None),
        )

    def test_result_is_hashable(self) -> None:
        {_index_key(("Mammals", ["Creatures", None]))}  # must not raise

    def test_tuple_and_list_spellings_normalize_identically(self) -> None:
        """A nested value may arrive as a list (from JSON) or a tuple (from
        natural_key()). If the two spellings diverged, a key stored via one
        would never be found via the other."""
        assert _index_key(("Wolf", ["Mammals", ["Creatures", None]])) == _index_key(
            ("Wolf", ("Mammals", ("Creatures", None)))
        )


class IndexRegistryTests(TestCase):
    """The registry is per-model and flushable."""

    def test_index_is_per_model_and_empty_by_default(self) -> None:
        assert natural_key_index(Species) == {}

    def test_index_owner_is_the_shared_dbclass(self) -> None:
        assert index_owner(Species) is Species.__dbclass__

    def test_flush_clears_entries_and_warm_flags(self) -> None:
        natural_key_index(Species)[("marker",)] = 999
        _NK_WARMED.add(index_owner(Species))
        flush_natural_key_indexes()
        assert natural_key_index(Species) == {}
        assert index_owner(Species) not in _NK_WARMED
