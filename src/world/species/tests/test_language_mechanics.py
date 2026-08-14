"""Tests for language mechanics (#2993): fluency bands, Language.trait link,
CG-finalize starting-language provisioning."""

from django.test import TestCase

from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.character_creation.services import finalize_magic_data
from world.character_sheets.factories import CharacterSheetFactory
from world.species.factories import SpeciesFactory
from world.species.language_constants import (
    FLUENT_GRANT_VALUE,
    Fluency,
    fluency_band,
)
from world.species.models import Language
from world.species.services import provision_starting_languages
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    Trait,
    TraitCategory,
    TraitType,
)


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


class ProvisionStartingLanguagesTest(TestCase):
    """Unit tests for provision_starting_languages (#2993)."""

    @classmethod
    def setUpTestData(cls) -> None:
        khatic_trait = Trait.objects.create(
            name="TestPSLKhatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.khatic = Language.objects.create(name="TestPSLKhatic", trait=khatic_trait)
        cls.species = SpeciesFactory(name="TestPSLSpecies")
        cls.species.starting_languages.add(cls.khatic)

        arvani_trait = Trait.objects.create(
            name="TestPSLArvani",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.arvani = Language.objects.create(
            name="TestPSLArvani", trait=arvani_trait, is_universal=True
        )

        cls.beginnings = BeginningsFactory()
        cls.sheet = CharacterSheetFactory(species=cls.species)

    def test_grants_universal_and_species_languages_at_fluent(self) -> None:
        granted = provision_starting_languages(self.sheet, beginnings=self.beginnings)
        values = {
            ctv.trait_id: ctv.value
            for ctv in CharacterTraitValue.objects.filter(character=self.sheet)
        }
        self.assertEqual(values[self.arvani.trait_id], FLUENT_GRANT_VALUE)
        self.assertEqual(values[self.khatic.trait_id], FLUENT_GRANT_VALUE)
        self.assertIn(self.arvani, granted)
        self.assertIn(self.khatic, granted)

    def test_misbegotten_flag_skips_species_language_but_keeps_universal(self) -> None:
        self.beginnings.grants_species_languages = False
        self.beginnings.save()
        provision_starting_languages(self.sheet, beginnings=self.beginnings)
        trait_ids = set(
            CharacterTraitValue.objects.filter(character=self.sheet).values_list(
                "trait_id", flat=True
            )
        )
        self.assertIn(self.arvani.trait_id, trait_ids)
        self.assertNotIn(self.khatic.trait_id, trait_ids)
        # Restore for other tests sharing setUpTestData's mutable beginnings row.
        self.beginnings.grants_species_languages = True
        self.beginnings.save()

    def test_idempotent_and_never_lowers(self) -> None:
        provision_starting_languages(self.sheet, beginnings=self.beginnings)
        ctv = CharacterTraitValue.objects.get(character=self.sheet, trait=self.arvani.trait)
        ctv.value = 90
        ctv.save()
        provision_starting_languages(self.sheet, beginnings=self.beginnings)
        ctv.refresh_from_db()
        self.assertEqual(ctv.value, 90)
        # Exactly one provenance row per language from CG.
        self.assertEqual(
            CharacterTraitChange.objects.filter(
                character_sheet=self.sheet, trait=self.arvani.trait
            ).count(),
            1,
        )

    def test_no_beginnings_still_grants_universal(self) -> None:
        granted = provision_starting_languages(self.sheet, beginnings=None)
        self.assertIn(self.arvani, granted)
        self.assertFalse(
            CharacterTraitValue.objects.filter(
                character=self.sheet, trait=self.khatic.trait
            ).exists()
        )


class ProvisionStartingLanguagesFinalizeIntegrationTest(TestCase):
    """Integration: finalize_magic_data wires provision_starting_languages (#2993)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import TraditionFactory

        khatic_trait = Trait.objects.create(
            name="TestPSLFinalizeKhatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.khatic = Language.objects.create(name="TestPSLFinalizeKhatic", trait=khatic_trait)
        cls.species = SpeciesFactory(name="TestPSLFinalizeSpecies")
        cls.species.starting_languages.add(cls.khatic)
        cls.beginnings = BeginningsFactory()
        cls.tradition = TraditionFactory()

    def test_finalize_magic_data_grants_starting_languages(self) -> None:
        sheet = CharacterSheetFactory(species=self.species)
        draft = CharacterDraftFactory(
            selected_tradition=self.tradition,
            selected_beginnings=self.beginnings,
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            CharacterTraitValue.objects.filter(character=sheet, trait=self.khatic.trait).exists(),
            "finalize_magic_data should provision the beginnings' starting languages",
        )
