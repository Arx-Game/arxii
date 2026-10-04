"""CharacterManifestation validation and admin (#4118)."""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.magic.admin import CharacterManifestationAdmin
from world.magic.factories import TechniqueFactory, TechniqueManifestOptionFactory
from world.magic.models import CharacterManifestation
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence


class CharacterManifestationCleanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory()
        cls.being = WorshippedBeingFactory()
        cls.archetype = CompanionArchetypeFactory()
        cls.being_option = TechniqueManifestOptionFactory(technique=cls.technique, being=cls.being)
        cls.archetype_option = TechniqueManifestOptionFactory(
            technique=cls.technique, being=None, archetype=cls.archetype
        )

    def _being_manifestation(self, **overrides):
        kwargs = {
            "character": self.sheet,
            "technique": self.technique,
            "option": self.being_option,
        }
        kwargs.update(overrides)
        return CharacterManifestation(**kwargs)

    def _patronage(self, **overrides):
        kwargs = {
            "character_sheet": self.sheet,
            "being": self.being,
            "valence": PatronageValence.DEVOTIONAL,
        }
        kwargs.update(overrides)
        return DevotionStandingFactory(**kwargs)

    def test_being_option_passes_with_active_patronage(self):
        self._patronage()
        self._being_manifestation().clean()

    def test_being_option_without_patronage_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            self._being_manifestation().clean()
        self.assertIn("option", ctx.exception.message_dict)

    def test_being_option_with_released_patronage_raises(self):
        self._patronage(released_at=timezone.now())
        with self.assertRaises(ValidationError):
            self._being_manifestation().clean()

    def test_ordinary_worship_is_not_a_bond(self):
        self._patronage(valence=None)
        with self.assertRaises(ValidationError):
            self._being_manifestation().clean()

    def test_option_of_another_technique_raises(self):
        other = TechniqueFactory()
        self._patronage()
        with self.assertRaises(ValidationError) as ctx:
            self._being_manifestation(technique=other).clean()
        self.assertIn("option", ctx.exception.message_dict)

    def test_being_option_with_companion_raises(self):
        self._patronage()
        companion = CompanionFactory(owner=self.sheet, archetype=self.archetype)
        with self.assertRaises(ValidationError) as ctx:
            self._being_manifestation(companion=companion).clean()
        self.assertIn("companion", ctx.exception.message_dict)

    def _archetype_manifestation(self, companion):
        return self._being_manifestation(option=self.archetype_option, companion=companion)

    def test_archetype_option_passes_with_owned_companion(self):
        companion = CompanionFactory(owner=self.sheet, archetype=self.archetype)
        self._archetype_manifestation(companion).clean()

    def test_archetype_option_without_companion_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            self._archetype_manifestation(None).clean()
        self.assertIn("companion", ctx.exception.message_dict)

    def test_archetype_option_with_others_companion_raises(self):
        companion = CompanionFactory(owner=CharacterSheetFactory(), archetype=self.archetype)
        with self.assertRaises(ValidationError):
            self._archetype_manifestation(companion).clean()

    def test_archetype_option_with_released_companion_raises(self):
        companion = CompanionFactory(
            owner=self.sheet, archetype=self.archetype, released_at=timezone.now()
        )
        with self.assertRaises(ValidationError):
            self._archetype_manifestation(companion).clean()

    def test_archetype_option_with_wrong_archetype_raises(self):
        companion = CompanionFactory(owner=self.sheet, archetype=CompanionArchetypeFactory())
        with self.assertRaises(ValidationError):
            self._archetype_manifestation(companion).clean()


class BondIsActiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory()
        cls.being = WorshippedBeingFactory()
        cls.archetype = CompanionArchetypeFactory()
        cls.being_option = TechniqueManifestOptionFactory(technique=cls.technique, being=cls.being)
        cls.archetype_option = TechniqueManifestOptionFactory(
            technique=cls.technique, being=None, archetype=cls.archetype
        )

    def test_flips_false_when_patronage_released(self):
        standing = DevotionStandingFactory(
            character_sheet=self.sheet, being=self.being, valence=PatronageValence.PACT
        )
        manifestation = CharacterManifestation(
            character=self.sheet, technique=self.technique, option=self.being_option
        )
        self.assertTrue(manifestation.bond_is_active())
        standing.released_at = timezone.now()
        standing.save()
        self.assertFalse(manifestation.bond_is_active())

    def test_flips_false_when_companion_released(self):
        companion = CompanionFactory(owner=self.sheet, archetype=self.archetype)
        manifestation = CharacterManifestation(
            character=self.sheet,
            technique=self.technique,
            option=self.archetype_option,
            companion=companion,
        )
        self.assertTrue(manifestation.bond_is_active())
        companion.released_at = timezone.now()
        companion.save()
        self.assertFalse(manifestation.bond_is_active())


class CharacterManifestationAdminFormTests(TestCase):
    def test_form_invalid_for_non_bonded_being(self):
        sheet = CharacterSheetFactory()
        option = TechniqueManifestOptionFactory()
        model_admin = admin.site._registry[CharacterManifestation]
        self.assertIsInstance(model_admin, CharacterManifestationAdmin)
        request = RequestFactory().get("/")
        request.user = AccountFactory(is_superuser=True, is_staff=True)
        form_class = model_admin.get_form(request, fields=["character", "technique", "option"])
        form = form_class(
            data={
                "character": sheet.pk,
                "technique": option.technique_id,
                "option": option.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("option", form.errors)
