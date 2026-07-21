"""Tests for the distinction earn-rate accelerator (#1834 Task 3)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.constants import (
    ACCELERATED_GAIN_SOURCES,
    NON_ACCELERATED_GAIN_SOURCES,
    GainSource,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    DistinctionResonanceGrantFactory,
    ResonanceFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.services.distinction_resonance import distinction_earn_rate_for
from world.magic.services.resonance import grant_resonance


class GainSourceTotalClassificationTests(TestCase):
    """Every GainSource member must fall into exactly one bucket (ADR-0041)."""

    def test_every_member_classified(self) -> None:
        self.assertEqual(
            set(GainSource),
            {GainSource(v) for v in ACCELERATED_GAIN_SOURCES}
            | {GainSource(v) for v in NON_ACCELERATED_GAIN_SOURCES},
        )

    def test_buckets_are_disjoint(self) -> None:
        self.assertEqual(
            set(ACCELERATED_GAIN_SOURCES) & set(NON_ACCELERATED_GAIN_SOURCES),
            set(),
        )


class DistinctionEarnRateForTests(TestCase):
    def test_no_distinction_returns_zero(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self.assertEqual(distinction_earn_rate_for(sheet, resonance), Decimal(0))

    def test_matching_distinction_returns_rank_scaled_bonus(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        distinction = DistinctionFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction,
            resonance=resonance,
            earn_rate_bonus_per_rank=Decimal("2.5"),
        )
        CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=2)

        self.assertEqual(distinction_earn_rate_for(sheet, resonance), Decimal("5.0"))

    def test_distinction_for_other_resonance_is_ignored(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        other_resonance = ResonanceFactory()
        distinction = DistinctionFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction,
            resonance=other_resonance,
            earn_rate_bonus_per_rank=Decimal("2.5"),
        )
        CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=2)

        self.assertEqual(distinction_earn_rate_for(sheet, resonance), Decimal(0))


class GrantResonanceAcceleratorTests(TestCase):
    def test_accelerated_source_scales_amount(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        distinction = DistinctionFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction,
            resonance=resonance,
            earn_rate_bonus_per_rank=Decimal("5.0"),
        )
        CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)
        cr = CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        grant_resonance(
            sheet,
            resonance,
            100,
            source=GainSource.ROOM_RESIDENCE,
            room_profile=_make_room_profile(),
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 105)
        self.assertEqual(cr.lifetime_earned, 105)
        grant = ResonanceGrant.objects.get(character_sheet=sheet, source=GainSource.ROOM_RESIDENCE)
        self.assertEqual(grant.amount, 105)

    def test_non_accelerated_source_stays_verbatim(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        distinction = DistinctionFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction,
            resonance=resonance,
            earn_rate_bonus_per_rank=Decimal("5.0"),
        )
        CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)
        character_distinction = CharacterDistinctionFactory(
            character=sheet, distinction=DistinctionFactory()
        )
        cr = CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        grant_resonance(
            sheet,
            resonance,
            100,
            source=GainSource.DISTINCTION,
            source_character_distinction=character_distinction,
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 100)
        self.assertEqual(cr.lifetime_earned, 100)

    def test_character_without_the_distinction_is_unscaled(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        distinction = DistinctionFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction,
            resonance=resonance,
            earn_rate_bonus_per_rank=Decimal("5.0"),
        )
        # No CharacterDistinction row for this sheet.
        cr = CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        grant_resonance(
            sheet,
            resonance,
            100,
            source=GainSource.ROOM_RESIDENCE,
            room_profile=_make_room_profile(),
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 100)
        self.assertEqual(cr.lifetime_earned, 100)


def _make_room_profile():
    from evennia_extensions.factories import RoomProfileFactory

    return RoomProfileFactory()
