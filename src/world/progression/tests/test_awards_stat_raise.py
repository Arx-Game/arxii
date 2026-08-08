"""``award_stat_raise`` (#3055 slice 1c): GM story reward -- a pure-fiat, no-tenure-
required counterpart to ``spend_level_stat_point`` that writes GM_GRANT provenance
instead of consuming a ``LevelStatPointSpend``.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.models import PathStage
from world.progression.models import MaturationStatCap
from world.progression.services.awards import award_stat_raise
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.factories import TraitFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    TraitChangeSource,
    TraitType,
)


class AwardStatRaiseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stat = TraitFactory(name="stat_award_test", trait_type=TraitType.STAT)
        cls.skill = TraitFactory(name="skill_award_test", trait_type=TraitType.SKILL)

    def _sheet(self):
        return CharacterSheetFactory()

    def _tenure(self):
        entry = RosterEntryFactory()
        return RosterTenureFactory(roster_entry=entry, end_date=None)

    def test_raises_stat_by_one_display_dot(self):
        sheet = self._sheet()
        tenure = self._tenure()
        change = award_stat_raise(sheet, self.stat, granting_tenure=tenure)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, STAT_DISPLAY_DIVISOR)
        self.assertEqual(change.old_value, 0)
        self.assertEqual(change.new_value, STAT_DISPLAY_DIVISOR)

    def test_writes_gm_grant_provenance_with_tenure(self):
        sheet = self._sheet()
        tenure = self._tenure()
        award_stat_raise(sheet, self.stat, granting_tenure=tenure)
        change = CharacterTraitChange.objects.get(character_sheet=sheet, trait=self.stat)
        self.assertEqual(change.source, TraitChangeSource.GM_GRANT)
        self.assertEqual(change.granting_tenure, tenure)

    def test_granting_tenure_may_be_none(self):
        """A staff-piloted GM with no roster tenure still succeeds (#3055 slice 1c)."""
        sheet = self._sheet()
        change = award_stat_raise(sheet, self.stat, granting_tenure=None)
        self.assertIsNone(change.granting_tenure)

    def test_non_stat_trait_raises_value_error(self):
        sheet = self._sheet()
        with self.assertRaises(ValueError):
            award_stat_raise(sheet, self.skill, granting_tenure=None)
        exists = CharacterTraitValue.objects.filter(character=sheet, trait=self.skill).exists()
        self.assertFalse(exists)

    def test_cap_reached_raises_value_error(self):
        sheet = self._sheet()
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=3)
        CharacterTraitValue.objects.create(
            character=sheet, trait=self.stat, value=3 * STAT_DISPLAY_DIVISOR
        )
        with self.assertRaises(ValueError):
            award_stat_raise(sheet, self.stat, granting_tenure=None)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, 3 * STAT_DISPLAY_DIVISOR)

    def test_repeated_raises_accumulate(self):
        sheet = self._sheet()
        award_stat_raise(sheet, self.stat, granting_tenure=None)
        award_stat_raise(sheet, self.stat, granting_tenure=None)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, 2 * STAT_DISPLAY_DIVISOR)
        self.assertEqual(
            CharacterTraitChange.objects.filter(
                character_sheet=sheet, trait=self.stat, source=TraitChangeSource.GM_GRANT
            ).count(),
            2,
        )
