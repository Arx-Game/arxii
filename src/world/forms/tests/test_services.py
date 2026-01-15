from django.test import TestCase

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
from world.forms.models import CharacterFormState, DurationType, FormType
from world.forms.services import (
    create_true_form,
    get_apparent_form,
    get_cg_form_options,
    revert_to_true_form,
    switch_form,
)
from world.species.factories import SpeciesFactory, SpeciesOriginFactory


class GetApparentFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.black_hair = FormTraitOptionFactory(
            trait=cls.hair_trait, name="black", display_name="Black"
        )
        cls.blonde_hair = FormTraitOptionFactory(
            trait=cls.hair_trait, name="blonde", display_name="Blonde"
        )

    def test_returns_base_form_values(self):
        form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=form, trait=self.hair_trait, option=self.black_hair)
        CharacterFormStateFactory(character=self.character, active_form=form)

        apparent = get_apparent_form(self.character)

        self.assertEqual(apparent[self.hair_trait], self.black_hair)

    def test_temporary_changes_override_base(self):
        form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=form, trait=self.hair_trait, option=self.black_hair)
        CharacterFormStateFactory(character=self.character, active_form=form)
        TemporaryFormChangeFactory(
            character=self.character,
            trait=self.hair_trait,
            option=self.blonde_hair,
            duration_type=DurationType.UNTIL_REMOVED,
        )

        apparent = get_apparent_form(self.character)

        self.assertEqual(apparent[self.hair_trait], self.blonde_hair)


class SwitchFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.other_character = CharacterFactory()

    def test_switch_form_updates_active_form(self):
        true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        alt_form = CharacterFormFactory(
            character=self.character, name="Beast", form_type=FormType.ALTERNATE
        )
        state = CharacterFormStateFactory(character=self.character, active_form=true_form)

        switch_form(self.character, alt_form)

        state.refresh_from_db()
        self.assertEqual(state.active_form, alt_form)

    def test_switch_form_raises_for_wrong_character(self):
        form = CharacterFormFactory(character=self.other_character, form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.character, active_form=None)

        with self.assertRaises(ValueError):
            switch_form(self.character, form)


class RevertToTrueFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()

    def test_revert_sets_true_form_active(self):
        true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        alt_form = CharacterFormFactory(character=self.character, form_type=FormType.ALTERNATE)
        state = CharacterFormStateFactory(character=self.character, active_form=alt_form)

        revert_to_true_form(self.character)

        state.refresh_from_db()
        self.assertEqual(state.active_form, true_form)


class GetCGFormOptionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="Human")
        cls.origin = SpeciesOriginFactory(species=cls.species, name="Arx")

        cls.hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.black = FormTraitOptionFactory(trait=cls.hair_trait, name="black", display_name="Black")
        cls.red = FormTraitOptionFactory(trait=cls.hair_trait, name="red", display_name="Red")
        cls.gray = FormTraitOptionFactory(trait=cls.hair_trait, name="gray", display_name="Gray")

        # Species has hair_color trait
        SpeciesFormTraitFactory(species=cls.species, trait=cls.hair_trait)

    def test_returns_all_options_without_origin_overrides(self):
        options = get_cg_form_options(self.species, self.origin)

        self.assertIn(self.hair_trait, options)
        trait_options = options[self.hair_trait]
        self.assertIn(self.black, trait_options)
        self.assertIn(self.red, trait_options)
        self.assertIn(self.gray, trait_options)

    def test_origin_can_remove_option(self):
        # Arx humans don't have red eyes
        SpeciesOriginTraitOptionFactory(
            species_origin=self.origin,
            option=self.red,
            is_available=False,
        )

        options = get_cg_form_options(self.species, self.origin)

        trait_options = options[self.hair_trait]
        self.assertNotIn(self.red, trait_options)
        self.assertIn(self.black, trait_options)

    def test_origin_can_add_option(self):
        # Create a new option only for this origin
        special = FormTraitOptionFactory(
            trait=self.hair_trait, name="special", display_name="Special"
        )
        SpeciesOriginTraitOptionFactory(
            species_origin=self.origin,
            option=special,
            is_available=True,
        )

        options = get_cg_form_options(self.species, self.origin)

        trait_options = options[self.hair_trait]
        self.assertIn(special, trait_options)


class CreateTrueFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.hair_trait = FormTraitFactory(name="hair_color")
        cls.black = FormTraitOptionFactory(trait=cls.hair_trait, name="black")
        cls.eye_trait = FormTraitFactory(name="eye_color")
        cls.blue = FormTraitOptionFactory(trait=cls.eye_trait, name="blue")

    def test_creates_true_form_with_values(self):
        selections = {
            self.hair_trait: self.black,
            self.eye_trait: self.blue,
        }

        form = create_true_form(self.character, selections)

        self.assertEqual(form.form_type, FormType.TRUE)
        self.assertEqual(form.character, self.character)
        self.assertEqual(form.values.count(), 2)

    def test_creates_form_state(self):
        selections = {self.hair_trait: self.black}

        form = create_true_form(self.character, selections)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, form)

    def test_raises_if_true_form_exists(self):
        CharacterFormFactory(character=self.character, form_type=FormType.TRUE)

        with self.assertRaises(ValueError):
            create_true_form(self.character, {})
