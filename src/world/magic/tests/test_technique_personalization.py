"""Hold lookups, display names and player-text hygiene (#4099)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import InvalidPersonalText
from world.magic.factories import (
    CharacterTechniqueFactory,
    PriceFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import MotifResonance
from world.magic.services.technique_personalization import (
    clean_custom_technique_description,
    clean_custom_technique_name,
    resolve_price_snippet,
    seed_motif_from_gift_resonance,
    technique_display_name,
    technique_price_for,
)


class NameHygieneTests(TestCase):
    def test_strips_and_collapses_whitespace(self) -> None:
        self.assertEqual(clean_custom_technique_name("  Winter   bite \n"), "Winter bite")

    def test_blank_means_the_catalog_name(self) -> None:
        self.assertEqual(clean_custom_technique_name("   "), "")

    def test_refuses_em_and_en_dashes(self) -> None:
        for bad in ("Winter—bite", "Winter–bite"):
            with self.assertRaises(InvalidPersonalText):
                clean_custom_technique_name(bad)

    def test_hyphen_is_fine(self) -> None:
        self.assertEqual(clean_custom_technique_name("Winter-bite"), "Winter-bite")

    def test_refuses_markup_and_control_characters(self) -> None:
        for bad in ("|rRed|n", "Bell\x07"):
            with self.assertRaises(InvalidPersonalText):
                clean_custom_technique_name(bad)

    def test_length_cap(self) -> None:
        with self.assertRaises(InvalidPersonalText):
            clean_custom_technique_name("x" * 81)

    def test_description_keeps_newlines_and_caps_length(self) -> None:
        self.assertEqual(clean_custom_technique_description(" a\nb "), "a\nb")
        with self.assertRaises(InvalidPersonalText):
            clean_custom_technique_description("x" * 2001)
        with self.assertRaises(InvalidPersonalText):
            clean_custom_technique_description("bad\x00")


class HoldReadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory(name="Scorch Lash")
        cls.price = PriceFactory(name="Frost on the skin", cast_narration="frost blooms white")
        cls.hold = CharacterTechniqueFactory(
            character=cls.sheet,
            technique=cls.technique,
            custom_name="Winterbite",
            price=cls.price,
        )

    def setUp(self) -> None:
        self.sheet.character.techniques.invalidate()

    def test_display_name_reads_the_hold(self) -> None:
        self.assertEqual(technique_display_name(self.sheet.character, self.technique), "Winterbite")

    def test_display_name_falls_back_for_an_unheld_technique(self) -> None:
        other = TechniqueFactory(name="Umbral Wall")
        self.assertEqual(technique_display_name(self.sheet.character, other), "Umbral Wall")
        self.assertEqual(
            technique_display_name(self.sheet.character, other, fallback="Wall, ash-formed"),
            "Wall, ash-formed",
        )

    def test_display_name_is_the_catalog_name_for_a_blank_custom_name(self) -> None:
        technique = TechniqueFactory(name="Ashfall Grasp")
        CharacterTechniqueFactory(character=self.sheet, technique=technique, custom_name="")
        self.sheet.character.techniques.invalidate()
        self.assertEqual(technique_display_name(self.sheet.character, technique), "Ashfall Grasp")

    def test_price_and_snippet(self) -> None:
        character = self.sheet.character
        self.assertEqual(technique_price_for(character, self.technique), self.price)
        self.assertEqual(resolve_price_snippet(character, self.technique), "frost blooms white")

    def test_snippet_falls_back_to_the_price_name(self) -> None:
        price = PriceFactory(name="Blood drawn", cast_narration="")
        technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.sheet, technique=technique, price=price)
        self.sheet.character.techniques.invalidate()
        self.assertEqual(resolve_price_snippet(self.sheet.character, technique), "Blood drawn")

    def test_price_flipped_to_design_kind_is_honored_no_longer(self) -> None:
        """A row staff later flip from PRICE to DESIGN grants nothing (#4099 final fix) -
        the hold's FK is stale; checked fresh against the row's current kind."""
        from world.magic.constants import RestrictionKind

        self.price.kind = RestrictionKind.DESIGN
        self.price.creation_point_cost = None
        self.price.save(update_fields=["kind", "creation_point_cost"])
        self.assertIsNone(technique_price_for(self.sheet.character, self.technique))
        self.assertIsNone(resolve_price_snippet(self.sheet.character, self.technique))

    def test_hold_lookup_is_cached(self) -> None:
        character = self.sheet.character
        character.techniques.hold_for(self.technique)
        with self.assertNumQueries(0):
            character.techniques.hold_for(self.technique)


class MotifSeedTests(TestCase):
    def test_seed_is_idempotent_and_marks_the_gift(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        first = seed_motif_from_gift_resonance(sheet, resonance)
        second = seed_motif_from_gift_resonance(sheet, resonance)
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(first.is_from_gift)
        self.assertEqual(MotifResonance.objects.filter(motif__character=sheet).count(), 1)
