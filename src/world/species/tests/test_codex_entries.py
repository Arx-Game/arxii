"""Species lineage and the codex entries it carries (#2880)."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory
from world.species.factories import SpeciesFactory


class SpeciesLineageTests(TestCase):
    """``Species.lineage`` walks ``parent`` from the species outward."""

    @classmethod
    def setUpTestData(cls):
        cls.khati = SpeciesFactory(name="LineageKhati")
        cls.vulpi = SpeciesFactory(name="LineageVulpi", parent=cls.khati)

    def test_root_species_lineage_is_itself(self):
        self.assertEqual(self.khati.lineage, [self.khati])

    def test_subspecies_lineage_runs_nearest_first(self):
        self.assertEqual(self.vulpi.lineage, [self.vulpi, self.khati])

    def test_lineage_terminates_on_a_parent_cycle(self):
        """A cycle is a data defect, not a hang: each species appears once."""
        self.khati.parent = self.vulpi
        self.khati.save()
        self.addCleanup(self._break_cycle)

        self.assertEqual(self.vulpi.lineage, [self.vulpi, self.khati])

    def _break_cycle(self):
        self.khati.parent = None
        self.khati.save()


class SpeciesCodexEntriesTests(TestCase):
    """``Species.codex_entries`` collects the lineage's entries, skipping gaps."""

    @classmethod
    def setUpTestData(cls):
        cls.umbrella_entry = CodexEntryFactory(name="The Umbrella Kind")
        cls.leaf_entry = CodexEntryFactory(name="The Leaf Kind")
        cls.umbrella = SpeciesFactory(name="CodexUmbrella", codex_entry=cls.umbrella_entry)
        cls.leaf = SpeciesFactory(name="CodexLeaf", parent=cls.umbrella, codex_entry=cls.leaf_entry)

    def test_subspecies_carries_its_own_entry_and_the_parents(self):
        self.assertEqual(self.leaf.codex_entries, [self.leaf_entry, self.umbrella_entry])

    def test_parent_without_an_entry_is_skipped_rather_than_yielding_none(self):
        unbound = SpeciesFactory(name="CodexUnbound", codex_entry=None)
        child = SpeciesFactory(name="CodexChild", parent=unbound, codex_entry=self.leaf_entry)

        self.assertEqual(child.codex_entries, [self.leaf_entry])

    def test_species_with_no_entry_anywhere_in_the_lineage_carries_none(self):
        unbound = SpeciesFactory(name="CodexUnboundRoot", codex_entry=None)

        self.assertEqual(unbound.codex_entries, [])
