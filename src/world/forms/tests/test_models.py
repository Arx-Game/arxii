from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    SpeciesFormTraitFactory,
    SpeciesOriginTraitOptionFactory,
    TemporaryFormChangeFactory,
)
from world.forms.models import DurationType, FormType, TemporaryFormChange, TraitType
from world.species.factories import SpeciesFactory, SpeciesOriginFactory


class FormTraitModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = FormTraitFactory(
            name="hair_color", display_name="Hair Color", trait_type=TraitType.COLOR
        )

    def test_str_returns_display_name(self):
        self.assertEqual(str(self.trait), "Hair Color")

    def test_trait_type_choices(self):
        self.assertEqual(self.trait.trait_type, TraitType.COLOR)


class FormTraitOptionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.option = FormTraitOptionFactory(trait=cls.trait, name="black", display_name="Black")

    def test_str_format(self):
        self.assertEqual(str(self.option), "Hair Color: Black")

    def test_unique_together_trait_name(self):
        from world.forms.models import FormTraitOption

        with self.assertRaises(IntegrityError):
            # Use create() directly to bypass django_get_or_create
            FormTraitOption.objects.create(trait=self.trait, name="black", display_name="Noir")


class SpeciesFormTraitModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="Human")
        cls.trait = FormTraitFactory(name="hair_color")
        cls.species_trait = SpeciesFormTraitFactory(species=cls.species, trait=cls.trait)

    def test_str_format(self):
        self.assertEqual(str(self.species_trait), "Human - Hair Color")


class SpeciesOriginTraitOptionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="Human")
        cls.origin = SpeciesOriginFactory(species=cls.species, name="Umbros")
        cls.trait = FormTraitFactory(name="eye_color")
        cls.option = FormTraitOptionFactory(trait=cls.trait, name="red", display_name="Red")
        cls.override = SpeciesOriginTraitOptionFactory(
            species_origin=cls.origin,
            trait=cls.trait,
            option=cls.option,
            is_available=True,
        )

    def test_str_shows_add_action(self):
        self.assertIn("+", str(self.override))

    def test_str_shows_remove_action(self):
        self.override.is_available = False
        self.override.save()
        self.assertIn("-", str(self.override))


class CharacterFormModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()

    def test_str_with_name(self):
        form = CharacterFormFactory(
            character=self.character, name="Beast Form", form_type=FormType.ALTERNATE
        )
        self.assertIn("Beast Form", str(form))

    def test_str_without_name(self):
        form = CharacterFormFactory(character=self.character, name="", form_type=FormType.TRUE)
        self.assertIn("True Form", str(form))


class CharacterFormValueModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()

    def test_str_format(self):
        trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        option = FormTraitOptionFactory(trait=trait, name="black", display_name="Black")
        form = CharacterFormFactory(character=self.character)
        value = CharacterFormValueFactory(form=form, trait=trait, option=option)
        self.assertIn("Hair Color", str(value))
        self.assertIn("Black", str(value))


class CharacterFormStateModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()

    def test_str_with_active_form(self):
        form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        state = CharacterFormStateFactory(character=self.character, active_form=form)
        self.assertIn(self.character.key, str(state))

    def test_str_without_active_form(self):
        state = CharacterFormStateFactory(character=self.character, active_form=None)
        self.assertIn("No active form", str(state))


class TemporaryFormChangeModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()

    def test_is_expired_until_removed_never_expires(self):
        change = TemporaryFormChangeFactory(
            character=self.character, duration_type=DurationType.UNTIL_REMOVED
        )
        self.assertFalse(change.is_expired())

    def test_is_expired_real_time_not_expired(self):
        change = TemporaryFormChangeFactory(
            character=self.character,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(change.is_expired())

    def test_is_expired_real_time_expired(self):
        change = TemporaryFormChangeFactory(
            character=self.character,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(change.is_expired())

    def test_active_manager_excludes_expired(self):
        # Create an expired change
        TemporaryFormChangeFactory(
            character=self.character,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        # Create an active change
        active = TemporaryFormChangeFactory(
            character=self.character,
            duration_type=DurationType.UNTIL_REMOVED,
        )
        active_changes = TemporaryFormChange.objects.active()
        self.assertIn(active, active_changes)
        self.assertEqual(active_changes.count(), 1)
