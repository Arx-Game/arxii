"""Tests for garble_text + comprehension services (#2993)."""

from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.species.language_constants import Fluency
from world.species.language_services import garble_text, render_speech, speech_seed
from world.species.models import Language
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType


class GarbleTextTest(SimpleTestCase):
    TEXT = "the caravan leaves at dawn through the salt gate"

    def test_full_ratio_returns_text(self) -> None:
        self.assertEqual(garble_text(self.TEXT, 1.0), self.TEXT)

    def test_zero_ratio_hides_everything(self) -> None:
        self.assertEqual(garble_text(self.TEXT, 0.0), "...")

    def test_deterministic_with_seed(self) -> None:
        a = garble_text(self.TEXT, 0.5, seed_key=speech_seed(7, self.TEXT))
        b = garble_text(self.TEXT, 0.5, seed_key=speech_seed(7, self.TEXT))
        self.assertEqual(a, b)

    def test_partial_ratio_leaks_some_but_not_all(self) -> None:
        out = garble_text(self.TEXT, 0.5, seed_key="x")
        self.assertNotEqual(out, self.TEXT)
        self.assertIn("...", out)

    def test_empty_text(self) -> None:
        self.assertEqual(garble_text("", 0.5), "...")


class RenderSpeechTest(TestCase):
    TEXT = "the caravan leaves at dawn through the salt gate"

    @classmethod
    def setUpTestData(cls) -> None:
        trait = Trait.objects.create(
            name="TestRenderSpeechKhatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = Language.objects.create(name="TestRenderSpeechKhatic", trait=trait)
        cls.fluent_sheet = CharacterSheetFactory()
        CharacterTraitValue.objects.create(character=cls.fluent_sheet, trait=trait, value=100)
        cls.zero_sheet = CharacterSheetFactory()

    def test_fluent_listener_gets_full_text(self) -> None:
        out = render_speech(
            self.TEXT,
            language=self.language,
            speaker_band=Fluency.FLUENT,
            listener_value=100,
        )
        self.assertEqual(out, self.TEXT)

    def test_zero_fluency_listener_gets_garble(self) -> None:
        out = render_speech(
            self.TEXT,
            language=self.language,
            speaker_band=Fluency.FLUENT,
            listener_value=0,
        )
        self.assertNotEqual(out, self.TEXT)

    def test_broken_speaker_caps_fluent_listener_below_full(self) -> None:
        out = render_speech(
            self.TEXT,
            language=self.language,
            speaker_band=Fluency.BROKEN,
            listener_value=100,
        )
        self.assertNotEqual(out, self.TEXT)
