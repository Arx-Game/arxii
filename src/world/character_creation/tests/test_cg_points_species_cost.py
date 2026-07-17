"""A costed species gift grant adds a 'species' line to the CG-points breakdown (#2472)."""

from django.test import TestCase

from world.character_creation.factories import CharacterDraftFactory
from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory


class SpeciesCgCostBreakdownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="TestCostedSpecies")
        SpeciesGiftGrantFactory(
            species=cls.species,
            gift=GiftFactory(name="Test Priced Gift", kind=GiftKind.MINOR),
            cg_point_cost=7,
        )

    def test_species_cost_appears_in_breakdown(self):
        draft = CharacterDraftFactory(selected_species=self.species)
        lines = draft.calculate_cg_points_breakdown()
        species_lines = [entry for entry in lines if entry["category"] == "species"]
        self.assertEqual(len(species_lines), 1)
        self.assertEqual(species_lines[0]["cost"], 7)

    def test_species_cost_reduces_remaining(self):
        draft = CharacterDraftFactory(selected_species=self.species)
        self.assertEqual(draft.calculate_cg_points_spent(), 7)

    def test_free_species_adds_no_line(self):
        free = SpeciesFactory(name="TestFreeSpecies")
        SpeciesGiftGrantFactory(
            species=free,
            gift=GiftFactory(name="Test Free Gift", kind=GiftKind.MINOR),
            cg_point_cost=0,
        )
        draft = CharacterDraftFactory(selected_species=free)
        species_lines = [
            e for e in draft.calculate_cg_points_breakdown() if e["category"] == "species"
        ]
        self.assertEqual(species_lines, [])
