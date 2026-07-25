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
from world.traits.factories import TraitFactory
from world.traits.models import TraitRankDescription


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


class CaseInsensitiveLookupTests(TestCase):
    """Natural-key text components match regardless of case (#2687)."""

    def test_differently_cased_lookup_finds_the_row(self) -> None:
        species = SpeciesFactory(name="Fire Elf")
        assert Species.objects.get_by_natural_key("fire elf") == species
        assert Species.objects.get_by_natural_key("FIRE ELF") == species

    def test_case_variants_share_one_index_entry(self) -> None:
        SpeciesFactory(name="Shared Entry Elf")
        Species.objects.get_by_natural_key("SHARED ENTRY ELF")
        with self.assertNumQueries(0):
            Species.objects.get_by_natural_key("shared entry elf")
        assert list(natural_key_index(Species)) == [("shared entry elf",)]

    def test_fk_and_text_components_combine_case_insensitively(self) -> None:
        """A composite key with an FK (species -> name) plus a plain CharField
        (stat) both match case-insensitively."""
        species = SpeciesFactory(name="Numeric Elf")
        bonus = SpeciesStatBonus.objects.create(species=species, stat="strength", value=2)
        found = SpeciesStatBonus.objects.get_by_natural_key("NUMERIC ELF", "STRENGTH")
        assert found == bonus

    def test_integer_component_matches_exactly(self) -> None:
        """__iexact applies only to text fields. The FK's name component matches
        case-insensitively; the integer component must still match exactly and
        must never be turned into a text comparison."""
        trait = TraitFactory(name="Rank Trait")
        description = TraitRankDescription.objects.create(
            trait=trait, value=30, label="Good", description="Above average"
        )
        assert TraitRankDescription.objects.get_by_natural_key("RANK TRAIT", 30) == description
        with self.assertRaises(TraitRankDescription.DoesNotExist):
            TraitRankDescription.objects.get_by_natural_key("Rank Trait", 31)

    def test_integer_component_gets_no_iexact_suffix(self) -> None:
        """Directly pins the branch: the lookup dict must key the integer field
        plainly, never as '<field>__iexact'."""
        TraitRankDescription.objects.create(
            trait=TraitFactory(name="Suffix Trait"),
            value=40,
            label="Great",
            description="x",
        )
        lookup = TraitRankDescription.objects._natural_key_lookup(("Suffix Trait", 40))
        assert "value" in lookup
        assert "value__iexact" not in lookup


class RenameInvalidationTests(TestCase):
    """A renamed row stops resolving under its old natural key."""

    def test_old_key_no_longer_resolves_after_rename(self) -> None:
        species = SpeciesFactory(name="Old Elf Name")
        Species.objects.get_by_natural_key("Old Elf Name")
        species.name = "New Elf Name"
        species.save()
        with self.assertRaises(Species.DoesNotExist):
            Species.objects.get_by_natural_key("Old Elf Name")
        assert Species.objects.get_by_natural_key("New Elf Name") == species

    def test_save_without_a_prior_lookup_is_harmless(self) -> None:
        species = SpeciesFactory(name="Never Looked Up")
        species.description = "changed"
        species.save()
        assert Species.objects.get_by_natural_key("Never Looked Up") == species
