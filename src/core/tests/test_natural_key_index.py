"""Tests for the natural-key → pk index in core.natural_keys (#2687)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from core.natural_keys import (
    _NK_WARMED,
    NaturalKeyConfigError,
    _index_key,
    flush_natural_key_indexes,
    index_owner,
    is_lookup_table,
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

    def test_rename_removes_the_old_key_from_the_index_dict(self) -> None:
        """Assert the dict itself, not just lookup behaviour — the SQLite fast
        tier has already been shown to let a behavioural assertion pass against a
        deliberately broken implementation."""
        species = SpeciesFactory(name="Dict Checked Elf")
        Species.objects.get_by_natural_key("Dict Checked Elf")
        assert ("dict checked elf",) in natural_key_index(Species)
        species.name = "Dict Checked Renamed"
        species.save()
        assert ("dict checked elf",) not in natural_key_index(Species)


def as_lookup_table(model: type):
    """Context manager opting *model* into lookup-table behaviour for one test.

    Task 5 builds the machinery; ConditionTemplate and Trait don't opt in until
    Tasks 6-7. Patching lets these tests exercise the warm without depending on
    a later task, so this task ends green on its own.
    """
    return patch.object(model.NaturalKeyConfig, "lookup_table", True, create=True)


class LookupTableTests(TestCase):
    """Opted-in models load whole and resolve from memory, never via iexact."""

    def test_opt_in_is_off_by_default(self) -> None:
        assert not is_lookup_table(Species)

    def test_warm_happens_once_then_lookups_are_free(self) -> None:
        SpeciesFactory(name="Warm One")
        SpeciesFactory(name="Warm Two")
        with as_lookup_table(Species):
            Species.objects.get_by_natural_key("Warm One")  # warms
            with self.assertNumQueries(0):
                Species.objects.get_by_natural_key("Warm One")
                Species.objects.get_by_natural_key("warm two")

    def test_miss_raises_without_falling_back_to_sql(self) -> None:
        SpeciesFactory(name="Present Elf")
        with as_lookup_table(Species):
            Species.objects.get_by_natural_key("Present Elf")  # warms
            with self.assertNumQueries(0), self.assertRaises(Species.DoesNotExist):
                Species.objects.get_by_natural_key("Absent Elf")

    def test_row_created_after_the_warm_is_findable(self) -> None:
        SpeciesFactory(name="Before Warm")
        with as_lookup_table(Species):
            Species.objects.get_by_natural_key("Before Warm")  # warms
            later = SpeciesFactory(name="After Warm")
            assert Species.objects.get_by_natural_key("after warm") == later

    def test_warm_raises_on_a_casefold_collision(self) -> None:
        """Two rows differing only in case are a content bug — fail loudly
        rather than letting one silently win the dict slot."""
        SpeciesFactory(name="Duplicate Elf")
        SpeciesFactory(name="duplicate elf")
        with as_lookup_table(Species):
            with self.assertRaises(NaturalKeyConfigError) as ctx:
                Species.objects.get_by_natural_key("Duplicate Elf")
        assert "duplicate elf" in str(ctx.exception).casefold()

    def test_stale_pk_triggers_one_rewarm(self) -> None:
        species = SpeciesFactory(name="Rewarm Me")
        with as_lookup_table(Species):
            Species.objects.get_by_natural_key("Rewarm Me")  # warms
            natural_key_index(Species)[("rewarm me",)] = 999_999
            assert Species.objects.get_by_natural_key("Rewarm Me") == species

    def test_fk_bearing_natural_key_is_rejected(self) -> None:
        """Warming calls natural_key() per row, which traverses FK descriptors —
        a query per row. Opting such a model in must fail loudly."""
        SpeciesStatBonus.objects.create(
            species=SpeciesFactory(name="FK Elf"), stat="strength", value=1
        )
        with as_lookup_table(SpeciesStatBonus):
            with self.assertRaises(NaturalKeyConfigError) as ctx:
                SpeciesStatBonus.objects.get_by_natural_key("FK Elf", "strength")
        message = str(ctx.exception)
        assert "lookup_table" in message
        assert "species" in message


class MroInvariantTests(TestCase):
    """Every NaturalKeyMixin model must reach NaturalKeyMixin.save() first.

    Uses Django's app registry rather than __subclasses__(): the registry is
    complete by construction, whereas __subclasses__() only sees classes Python
    has already imported, so a model could silently escape this check purely
    because no test in the run happened to import it.
    """

    def test_mixin_precedes_sharedmemorymodel_in_every_model_mro(self) -> None:
        from django.apps import apps
        from evennia.utils.idmapper.models import SharedMemoryModel

        from core.natural_keys import NaturalKeyMixin

        checked = 0
        offenders = []
        for model in apps.get_models():
            mro = model.__mro__
            if NaturalKeyMixin not in mro or SharedMemoryModel not in mro:
                continue
            checked += 1
            if mro.index(NaturalKeyMixin) > mro.index(SharedMemoryModel):
                offenders.append(model.__name__)
        assert not offenders, (
            "NaturalKeyMixin must precede SharedMemoryModel in the MRO or its "
            f"save() invalidation never runs. Offenders: {offenders}"
        )
        # Guard against the guard silently checking nothing.
        assert checked > 150, f"expected ~181 NaturalKeyMixin models, checked {checked}"
