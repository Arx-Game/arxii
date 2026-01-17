from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.forms.factories import (
    BuildFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    HeightBandFactory,
    SpeciesFormTraitFactory,
    TemporaryFormChangeFactory,
)
from world.forms.models import DurationType, FormType, TemporaryFormChange, TraitType
from world.species.factories import SpeciesFactory


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


class HeightBandModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.band = HeightBandFactory(
            name="average",
            display_name="Average",
            min_inches=68,
            max_inches=71,
        )

    def test_str_returns_display_name(self):
        self.assertEqual(str(self.band), "Average")

    def test_midpoint_calculation(self):
        # (68 + 71) // 2 = 69
        self.assertEqual(self.band.midpoint, 69)

    def test_midpoint_rounds_down(self):
        band = HeightBandFactory(name="test_band", min_inches=60, max_inches=65)
        # (60 + 65) // 2 = 62
        self.assertEqual(band.midpoint, 62)


class BuildModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build = BuildFactory(
            name="athletic",
            display_name="Athletic",
            weight_factor=Decimal("2.5"),
        )

    def test_str_returns_display_name(self):
        self.assertEqual(str(self.build), "Athletic")

    def test_weight_factor_stored(self):
        self.assertEqual(self.build.weight_factor, Decimal("2.5"))


class FormTraitOptionHeightModifierTest(TestCase):
    def test_height_modifier_default_null(self):
        option = FormTraitOptionFactory()
        self.assertIsNone(option.height_modifier_inches)

    def test_height_modifier_can_be_set(self):
        option = FormTraitOptionFactory(height_modifier_inches=4)
        self.assertEqual(option.height_modifier_inches, 4)

    def test_height_modifier_can_be_negative(self):
        # For traits that reduce apparent height
        option = FormTraitOptionFactory(height_modifier_inches=-2)
        self.assertEqual(option.height_modifier_inches, -2)
