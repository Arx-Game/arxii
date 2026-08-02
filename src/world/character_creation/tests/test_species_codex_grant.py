"""Tests for _finalize_species_codex: the species codex grant walks Species.parent.

Before #2880 the grant read ``sheet.species.codex_entry`` and nothing else, so a
Vulpi character received the Vulpi entry and never the Khati umbrella entry the
whole Khati set is written to sit under. Ruled 2026-08-02 (Tehom, ``umbrella-grant
= walk``): grant the parent chain too.
"""

from django.test import TestCase

from world.character_creation.services import _finalize_species_codex
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.roster.factories import RosterEntryFactory
from world.species.factories import SpeciesFactory


class FinalizeSpeciesCodexTests(TestCase):
    """The grant covers the character's species and every ancestor of it."""

    @classmethod
    def setUpTestData(cls):
        cls.umbrella_entry = CodexEntryFactory(name="The Grant Umbrella")
        cls.kind_entry = CodexEntryFactory(name="The Grant Kind")
        cls.umbrella = SpeciesFactory(name="GrantUmbrella", codex_entry=cls.umbrella_entry)
        cls.kind = SpeciesFactory(name="GrantKind", parent=cls.umbrella, codex_entry=cls.kind_entry)

    def _sheet_for(self, species):
        sheet = CharacterSheetFactory(species=species)
        RosterEntryFactory(character_sheet__character=sheet.character)
        sheet.refresh_from_db()
        return sheet

    def _known_entry_ids(self, sheet):
        return set(
            CharacterCodexKnowledge.objects.filter(roster_entry=sheet.roster_entry).values_list(
                "entry_id", flat=True
            )
        )

    def test_subspecies_receives_the_umbrella_entry_as_well(self):
        sheet = self._sheet_for(self.kind)

        _finalize_species_codex(sheet)

        self.assertEqual(
            self._known_entry_ids(sheet),
            {self.kind_entry.pk, self.umbrella_entry.pk},
        )

    def test_granted_entries_are_known(self):
        sheet = self._sheet_for(self.kind)

        _finalize_species_codex(sheet)

        statuses = set(
            CharacterCodexKnowledge.objects.filter(roster_entry=sheet.roster_entry).values_list(
                "status", flat=True
            )
        )
        self.assertEqual(statuses, {CodexKnowledgeStatus.KNOWN})

    def test_root_species_receives_only_its_own_entry(self):
        sheet = self._sheet_for(self.umbrella)

        _finalize_species_codex(sheet)

        self.assertEqual(self._known_entry_ids(sheet), {self.umbrella_entry.pk})

    def test_unbound_parent_does_not_block_the_child_grant(self):
        """Saurian-shaped case: an ancestor with codex_entry still null."""
        unbound = SpeciesFactory(name="GrantUnbound", codex_entry=None)
        child = SpeciesFactory(name="GrantChild", parent=unbound, codex_entry=self.kind_entry)
        sheet = self._sheet_for(child)

        _finalize_species_codex(sheet)

        self.assertEqual(self._known_entry_ids(sheet), {self.kind_entry.pk})

    def test_species_without_any_entry_is_a_noop(self):
        unbound = SpeciesFactory(name="GrantUnboundRoot", codex_entry=None)
        sheet = self._sheet_for(unbound)

        _finalize_species_codex(sheet)

        self.assertEqual(self._known_entry_ids(sheet), set())

    def test_double_call_creates_one_row_per_entry(self):
        sheet = self._sheet_for(self.kind)

        _finalize_species_codex(sheet)
        _finalize_species_codex(sheet)

        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(roster_entry=sheet.roster_entry).count(),
            2,
        )
