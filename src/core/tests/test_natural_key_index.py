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
from world.species.factories import SpeciesFactory
from world.species.models import Species, SpeciesStatBonus


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


class LazyIndexTests(TestCase):
    """Non-lookup-table models fill the index on lookup."""

    def test_repeat_lookup_issues_no_queries(self) -> None:
        species = SpeciesFactory(name="Indexed Elf")
        Species.objects.get_by_natural_key("Indexed Elf")  # priming call
        with self.assertNumQueries(0):
            result = Species.objects.get_by_natural_key("Indexed Elf")
        assert result == species

    def test_first_lookup_populates_the_index(self) -> None:
        species = SpeciesFactory(name="Recorded Elf")
        Species.objects.get_by_natural_key("Recorded Elf")
        assert natural_key_index(Species)[("recorded elf",)] == species.pk

    def test_composite_key_repeat_lookup_issues_no_queries(self) -> None:
        """A hit short-circuits BEFORE the recursive FK resolution, so a
        composite key costs nothing on repeat — not even the FK's own lookup."""
        species = SpeciesFactory(name="Composite Elf")
        SpeciesStatBonus.objects.create(species=species, stat="strength", value=1)
        SpeciesStatBonus.objects.get_by_natural_key("Composite Elf", "strength")
        with self.assertNumQueries(0):
            result = SpeciesStatBonus.objects.get_by_natural_key("Composite Elf", "strength")
        assert result.value == 1

    def test_missing_row_is_not_cached(self) -> None:
        with self.assertRaises(Species.DoesNotExist):
            Species.objects.get_by_natural_key("Not Yet Created")
        assert ("not yet created",) not in natural_key_index(Species)
        species = SpeciesFactory(name="Not Yet Created")
        assert Species.objects.get_by_natural_key("Not Yet Created") == species

    def test_deleted_row_self_heals(self) -> None:
        """A dead pk raises DoesNotExist on the by-pk fetch; the entry is
        dropped and the natural-key query re-run (which then also misses)."""
        species = SpeciesFactory(name="Doomed Elf")
        Species.objects.get_by_natural_key("Doomed Elf")
        Species.objects.filter(pk=species.pk).delete()
        with self.assertRaises(Species.DoesNotExist):
            Species.objects.get_by_natural_key("Doomed Elf")


class IndexIsolationTests(TestCase):
    """Companion pair: proves the test-runner flush clears the index."""

    def test_a_seeds_the_index(self) -> None:
        SpeciesFactory(name="Isolation Marker Species")
        Species.objects.get_by_natural_key("Isolation Marker Species")
        assert ("isolation marker species",) in natural_key_index(Species)

    def test_b_starts_clean(self) -> None:
        assert ("isolation marker species",) not in natural_key_index(Species)
