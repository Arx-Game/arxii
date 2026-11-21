"""The share of a cast's corruption a caster takes, by how Abyssal she is (#5231).

The step lookup is read at its boundary here, which no journey can probe: with the starting
numbers (light part 10, full from an Abyssal share of 50) a caster at 49.99 takes a tenth and
one at exactly 50 takes all of it.
"""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAuraFactory,
    CorruptionConfigFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models.affinity import Affinity
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.services.corruption import cast_corruption_part


class TestCastCorruptionPart(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        Affinity.objects.clear_cache()
        ensure_canonical_affinities()
        cls.config = CorruptionConfigFactory()

    def _caster_with_abyssal_share(self, abyssal: str):
        sheet = CharacterSheetFactory()
        aura = CharacterAuraFactory(character=sheet)
        primal = str(Decimal(100) - Decimal(abyssal))
        set_aura_split(aura, celestial="0", primal=primal, abyssal=abyssal)
        return sheet

    def test_the_light_part_below_the_line_and_all_of_it_from_the_line(self) -> None:
        for abyssal, expected in (("49.99", 10), ("50.00", 100), ("80", 100)):
            with self.subTest(abyssal=abyssal):
                sheet = self._caster_with_abyssal_share(abyssal)
                self.assertEqual(cast_corruption_part(sheet, self.config), expected)

    def test_a_sheet_with_no_aura_takes_all_of_it(self) -> None:
        self.assertEqual(cast_corruption_part(CharacterSheetFactory(), self.config), 100)

    def test_a_light_part_of_a_hundred_takes_all_of_it_at_any_share(self) -> None:
        # Unsaved: the factory hands back the shared singleton row, which must stay at 10.
        config = CorruptionConfig(light_corruption_percent=100, full_corruption_from_share=50)
        sheet = self._caster_with_abyssal_share("20")
        self.assertEqual(cast_corruption_part(sheet, config), 100)


class TestCastCorruptionPartWithoutAbyssalAffinity(TestCase):
    """A game with no Abyssal affinity row takes the full part and never raises."""

    def test_a_missing_abyssal_row_takes_all_of_it(self) -> None:
        Affinity.objects.clear_cache()
        sheet = CharacterSheetFactory()
        # An aura of Primal only: the factory writes no row for a share of zero.
        CharacterAuraFactory(
            character=sheet, celestial=Decimal(0), primal=Decimal(100), abyssal=Decimal(0)
        )
        self.assertFalse(Affinity.objects.filter(name="Abyssal").exists())
        self.assertEqual(cast_corruption_part(sheet, CorruptionConfigFactory()), 100)
