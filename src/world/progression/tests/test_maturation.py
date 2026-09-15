"""Maturation Points (#2756): deterministic milestones funded by matured years.

The points live in the years themselves: a spend is active iff its
milestone_year <= the sheet's current matured_years, so freeze/reversal/
catch-up all reduce to one comparison.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.models import PathStage
from world.progression.exceptions import (
    MaturationCapReachedError,
    MaturationNoPointsError,
    MaturationNotAStatError,
)
from world.progression.models import MaturationSpend, MaturationStatCap
from world.progression.services.maturation import (
    available_points,
    milestone_count,
    next_milestone_year,
    spend_maturation_point,
    sync_maturation_spends,
)
from world.species.factories import SpeciesFactory
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitValue, TraitCategory, TraitType


class MilestoneArithmeticTests(TestCase):
    def test_milestones_widen_with_age_and_stop_at_seventy_five(self):
        # 24, 27, 30 / 34, 38, 42 / 47, 52 / 58, 64 / 75 (#3635); 21 is not a milestone.
        cases = [
            (18, 0),
            (21, 0),
            (23, 0),
            (24, 1),
            (30, 3),
            (33, 3),
            (42, 6),
            (64, 10),
            (75, 11),
            (90, 11),
        ]
        for matured, expected in cases:
            with self.subTest(matured=matured):
                self.assertEqual(milestone_count(matured), expected)


class NextMilestoneTests(TestCase):
    def test_next_milestone_is_the_first_year_ahead_or_none(self):
        self.assertEqual(next_milestone_year(18), 24)
        self.assertEqual(next_milestone_year(24), 27)
        self.assertEqual(next_milestone_year(70), 75)
        self.assertIsNone(next_milestone_year(75))


class MaturationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mortal = SpeciesFactory(name="Human (maturation test)")
        cls.elf = SpeciesFactory(
            name="Elf (maturation test)", eternal_youth=True, decline_start_age=None
        )
        cls.stat = TraitFactory(
            name="stamina_maturation_test",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        cls.skill = TraitFactory(name="skill_maturation_test", trait_type=TraitType.SKILL)
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5)
        MaturationStatCap.objects.create(path_stage=PathStage.POTENTIAL, stat_cap=6)

    def _sheet(self, matured=30, species=None):
        sheet = CharacterSheetFactory(matured_years=matured, withered_years=0)
        sheet.species = species or self.mortal
        sheet.save()
        return sheet

    def test_available_points_counts_unspent_milestones(self):
        sheet = self._sheet(matured=30)  # milestones at 24/27/30
        self.assertEqual(available_points(sheet), 3)

    def test_eternal_youth_species_has_no_points(self):
        sheet = self._sheet(matured=29, species=self.elf)
        self.assertEqual(available_points(sheet), 0)

    def test_spend_raises_stat_value_and_consumes_lowest_milestone(self):
        sheet = self._sheet(matured=24)
        # Stat storage is internal ×10 (#2894): display 3 = 30.
        CharacterTraitValue.objects.create(character=sheet, trait=self.stat, value=30)

        spend = spend_maturation_point(sheet, self.stat)

        self.assertEqual(spend.milestone_year, 24)
        self.assertTrue(spend.is_active)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, 40)
        self.assertEqual(available_points(sheet), 0)

    def test_spend_without_points_raises(self):
        sheet = self._sheet(matured=23)
        with self.assertRaises(MaturationNoPointsError):
            spend_maturation_point(sheet, self.stat)

    def test_spend_past_stage_cap_raises(self):
        sheet = self._sheet(matured=24)  # level 1 -> PROSPECT cap 5 display dots
        CharacterTraitValue.objects.create(character=sheet, trait=self.stat, value=50)
        with self.assertRaises(MaturationCapReachedError):
            spend_maturation_point(sheet, self.stat)

    def test_spend_on_non_stat_trait_raises(self):
        sheet = self._sheet(matured=24)
        with self.assertRaises(MaturationNotAStatError):
            spend_maturation_point(sheet, self.skill)

    def test_reversal_deactivates_spends_and_reaging_reactivates(self):
        sheet = self._sheet(matured=27)  # milestones 24, 27
        CharacterTraitValue.objects.create(character=sheet, trait=self.stat, value=10)
        spend_maturation_point(sheet, self.stat)
        spend_maturation_point(sheet, self.stat)
        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value, 30
        )

        # True age-reversal magic winds back to 25: year 27's point lifts off.
        sheet.matured_years = 25
        sheet.save()
        sync_maturation_spends(sheet)

        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value, 20
        )
        self.assertEqual(
            MaturationSpend.objects.filter(character_sheet=sheet, is_active=True).count(), 1
        )
        self.assertEqual(available_points(sheet), 0)  # milestone 24 spent, no more earned

        # Aging back to 27 restores the year, and its point.
        sheet.matured_years = 27
        sheet.save()
        sync_maturation_spends(sheet)

        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value, 30
        )
        self.assertEqual(available_points(sheet), 0)
