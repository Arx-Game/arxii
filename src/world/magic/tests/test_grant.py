from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    EntryFlourishRecordFactory,
    ResonanceFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.services.resonance import grant_resonance


class ResonanceGrantEntryFlourishTest(TestCase):
    def test_grant_entry_flourish_creates_ledger_row(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        record = EntryFlourishRecordFactory(
            character_sheet=sheet, resonance=resonance, granted_amount=10
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )
        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.ENTRY_FLOURISH,
            entry_flourish=record,
        )
        grant = ResonanceGrant.objects.get(source=GainSource.ENTRY_FLOURISH)
        self.assertEqual(grant.source_entry_flourish, record)

    def test_grant_dramatic_moment_creates_ledger_row(self):
        sheet = CharacterSheetFactory()
        tag = DramaticMomentTagFactory(character_sheet=sheet)
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=tag.moment_type.resonance, balance=0, lifetime_earned=0
        )
        grant_resonance(
            sheet,
            tag.moment_type.resonance,
            15,
            source=GainSource.DRAMATIC_MOMENT,
            dramatic_moment=tag,
        )
        grant = ResonanceGrant.objects.get(source=GainSource.DRAMATIC_MOMENT)
        self.assertEqual(grant.source_dramatic_moment, tag)

    def test_grant_resonance_mission_reward_source_requires_line(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )
        with self.assertRaises(ValueError):
            grant_resonance(
                sheet,
                resonance,
                10,
                source=GainSource.MISSION_REWARD,
            )

    def test_grant_resonance_mission_reward_source_writes_typed_fk(self):
        from world.missions.factories import MissionDeedRewardLineFactory

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )
        line = MissionDeedRewardLineFactory(resonance=resonance, amount=10)
        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.MISSION_REWARD,
            mission_deed_reward_line=line,
        )
        grant = ResonanceGrant.objects.get(character_sheet=sheet, source=GainSource.MISSION_REWARD)
        assert grant.source_mission_deed_reward_line_id == line.pk
