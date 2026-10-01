"""A sheet read shows the player's own names (spec test seam, #4099)."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

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
from world.magic.services.technique_forms import next_signatures_by_technique


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

    def test_build_magic_query_count_holds_with_a_priced_hold_and_technique_thread(
        self,
    ) -> None:
        """#4099 fix round 1: pin the query count for the fully-personalized case.

        The original pin (``test_viewset.py``'s ``test_magic_zero_queries``) uses a
        fixture with no price and no TECHNIQUE thread, so it could not prove the
        ``price``/``early_form`` select_related actually rides the existing prefetch
        once those rows are populated. This fixture has both.
        """
        sheet = get_character_sheet_queryset().get(pk=self.sheet.pk)
        sheet.character.threads.invalidate()
        with CaptureQueriesContext(connection) as ctx:
            _build_magic(sheet)
        self.assertLessEqual(
            len(ctx.captured_queries),
            4,
            f"_build_magic issued {len(ctx.captured_queries)} queries: "
            f"{[q['sql'] for q in ctx.captured_queries]}",
        )


class NextSignaturesByTechniqueTieBreakTests(TestCase):
    """#4099 fix round 1: several TECHNIQUE threads on one technique pick deterministically.

    ``uniq_thread_technique`` allows more than one TECHNIQUE thread per
    ``(owner, target_technique)`` as long as the resonance differs, so a
    multi-resonance caster can hold two threads naming the same technique. The
    pick must not depend on dict-overwrite (iteration) order.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        gift = GiftFactory()
        CharacterGiftFactory(character=cls.sheet, gift=gift)
        cls.technique = TechniqueFactory(gift=gift, name="Scorch Lash", level=1)
        cls.resonance_a = ResonanceFactory()
        cls.resonance_b = ResonanceFactory()

    def _threads(self) -> None:
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_a,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=1,
        )
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=1,
        )

    def test_picks_the_lowest_min_crossing_level(self) -> None:
        self._threads()
        SignatureMotifBonusFactory(
            name="Farther flourish", required_resonance=self.resonance_a, min_crossing_level=6
        )
        SignatureMotifBonusFactory(
            name="Nearer flourish", required_resonance=self.resonance_b, min_crossing_level=3
        )

        result = next_signatures_by_technique(self.sheet.character)

        self.assertEqual(result[self.technique.pk]["name"], "Nearer flourish")
        self.assertEqual(result[self.technique.pk]["min_level"], 3)

    def test_ties_on_level_break_by_name(self) -> None:
        self._threads()
        SignatureMotifBonusFactory(
            name="Zed flourish", required_resonance=self.resonance_a, min_crossing_level=3
        )
        SignatureMotifBonusFactory(
            name="Able flourish", required_resonance=self.resonance_b, min_crossing_level=3
        )

        result = next_signatures_by_technique(self.sheet.character)

        self.assertEqual(result[self.technique.pk]["name"], "Able flourish")
