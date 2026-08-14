"""Tests for language mechanics (#2993): fluency bands, Language.trait link."""

from django.test import TestCase

from world.species.language_constants import (
    FLUENT_GRANT_VALUE,
    Fluency,
    fluency_band,
)
from world.species.models import Language
from world.traits.models import Trait, TraitCategory, TraitType


class FluencyBandTest(TestCase):
    def test_bands(self) -> None:
        self.assertEqual(fluency_band(0), Fluency.NONE)
        self.assertEqual(fluency_band(1), Fluency.BROKEN)
        self.assertEqual(fluency_band(29), Fluency.BROKEN)
        self.assertEqual(fluency_band(30), Fluency.CONVERSATIONAL)
        self.assertEqual(fluency_band(69), Fluency.CONVERSATIONAL)
        self.assertEqual(fluency_band(FLUENT_GRANT_VALUE), Fluency.FLUENT)
        self.assertEqual(fluency_band(100), Fluency.FLUENT)


class LanguageTraitLinkTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = Trait.objects.create(
            name="Khatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = Language.objects.create(name="Khatic", trait=cls.trait)

    def test_language_links_trait(self) -> None:
        self.assertEqual(self.language.trait, self.trait)
        self.assertEqual(self.trait.language, self.language)

    def test_is_universal_default_false(self) -> None:
        self.assertFalse(self.language.is_universal)
