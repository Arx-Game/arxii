"""A sheet read shows the player's own names (spec test seam, #4099)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.serializers import _build_magic, get_character_sheet_queryset
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    PriceFactory,
    ResonanceFactory,
    SignatureMotifBonusFactory,
    TechniqueFactory,
)
from world.magic.models import Thread


class SheetPersonalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        gift = GiftFactory()
        CharacterGiftFactory(character=cls.sheet, gift=gift)
        cls.resonance = ResonanceFactory()
        cls.technique = TechniqueFactory(gift=gift, name="Scorch Lash", level=1)
        CharacterTechniqueFactory(
            character=cls.sheet,
            technique=cls.technique,
            custom_name="Winterbite",
            custom_description="Flame gutters to white.",
            price=PriceFactory(name="Frost on the skin", power_bonus=4),
        )
        Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=cls.technique,
            level=1,
        )
        cls.next_flourish = SignatureMotifBonusFactory(
            name="Rime walks with you", required_resonance=cls.resonance, min_crossing_level=3
        )

    def _technique_entry(self):
        sheet = get_character_sheet_queryset().get(pk=self.sheet.pk)
        sheet.character.threads.invalidate()
        magic = _build_magic(sheet)
        return magic["gifts"][0]["techniques"][0]

    def test_entry_shows_the_players_name_and_description(self) -> None:
        entry = self._technique_entry()
        self.assertEqual(entry["name"], "Winterbite")
        self.assertEqual(entry["catalog_name"], "Scorch Lash")
        self.assertEqual(entry["description"], "Flame gutters to white.")

    def test_entry_shows_price_and_next_flourish(self) -> None:
        entry = self._technique_entry()
        self.assertEqual(entry["price"]["name"], "Frost on the skin")
        self.assertEqual(entry["next_signature"]["name"], "Rime walks with you")
        self.assertEqual(entry["next_signature"]["min_level"], 3)
