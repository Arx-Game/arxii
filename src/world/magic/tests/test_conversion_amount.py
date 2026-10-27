"""convert_resonance_amount: the single-resonance conversion primitive (slice 4 of #4672)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.services.conversion import convert_resonance_amount


class ConvertResonanceAmountTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.abyssal = ResonanceFactory(affinity=AffinityFactory(name="Abyssal"))
        cls.celestial = ResonanceFactory(affinity=AffinityFactory(name="Celestial"))
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.abyssal,
            balance=20,
            lifetime_earned=40,
        )

    def _convert(self, amount: int, multiplier: str) -> tuple[int, int]:
        return convert_resonance_amount(
            self.sheet,
            source_resonance=self.abyssal,
            target_resonance=self.celestial,
            amount=amount,
            multiplier=Decimal(multiplier),
            gain_source=GainSource.DRIFT_CORRECTION,
        )

    def _row(self, resonance) -> CharacterResonance:
        return CharacterResonance.objects.get(character_sheet=self.sheet, resonance=resonance)

    def test_moves_proportional_lifetime_and_writes_one_grant(self) -> None:
        result = self._convert(10, "0.5")

        self.assertEqual(result, (5, 20))
        source = self._row(self.abyssal)
        self.assertEqual((source.balance, source.lifetime_earned), (10, 20))
        target = self._row(self.celestial)
        self.assertEqual((target.balance, target.lifetime_earned), (5, 20))
        grants = ResonanceGrant.objects.filter(
            character_sheet=self.sheet, source=GainSource.DRIFT_CORRECTION
        )
        self.assertEqual([g.amount for g in grants], [5])

    def test_multiplier_flooring_to_zero_still_grants_one(self) -> None:
        result = self._convert(1, "0.5")

        self.assertEqual(result[0], 1)
        self.assertEqual(self._row(self.celestial).balance, 1)
        self.assertEqual(self._row(self.abyssal).balance, 19)

    def test_amount_over_balance_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._convert(21, "0.5")
        self.assertEqual(self._row(self.abyssal).balance, 20)

    def test_non_positive_amount_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._convert(0, "0.5")
