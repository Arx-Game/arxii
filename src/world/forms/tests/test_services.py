from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    BuildFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    HeightBandFactory,
    SpeciesFormTraitFactory,
    SpeciesOriginTraitOptionFactory,
    TemporaryFormChangeFactory,
)
from world.forms.models import CharacterFormState, DurationType, FormType
from world.forms.services import (
    calculate_weight,
    create_true_form,
    get_apparent_build,
    get_apparent_form,
    get_apparent_height,
    get_cg_builds,
    get_cg_form_options,
    get_cg_height_bands,
    get_height_band,
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


# --- Height/Build Service Function Tests ---


class GetHeightBandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clear any existing height bands to avoid conflicts with migration data
        from world.forms.models import HeightBand

        HeightBand.objects.all().delete()
        cls.short = HeightBandFactory(name="short", min_inches=60, max_inches=66)
        cls.average = HeightBandFactory(name="average", min_inches=67, max_inches=72)
        cls.tall = HeightBandFactory(name="tall", min_inches=73, max_inches=82)

    def test_returns_matching_band(self):
        band = get_height_band(70)
        self.assertEqual(band, self.average)

    def test_returns_band_at_min_boundary(self):
        band = get_height_band(67)
        self.assertEqual(band, self.average)

    def test_returns_band_at_max_boundary(self):
        band = get_height_band(72)
        self.assertEqual(band, self.average)

    def test_returns_none_if_no_match(self):
        band = get_height_band(50)
        self.assertIsNone(band)


class CalculateWeightTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clear existing data to avoid conflicts with migration data
        from world.forms.models import Build, HeightBand

        HeightBand.objects.all().delete()
        Build.objects.all().delete()
        cls.average_band = HeightBandFactory(name="average", min_inches=67, max_inches=72)
        cls.tiny_band = HeightBandFactory(name="tiny", min_inches=12, max_inches=35, weight_max=60)
        cls.colossal_band = HeightBandFactory(
            name="colossal", min_inches=145, max_inches=300, weight_min=400
        )
        cls.athletic = BuildFactory(name="athletic", weight_factor=Decimal("2.5"))
        cls.brawny = BuildFactory(name="brawny", weight_factor=Decimal("3.0"))

    def test_basic_weight_calculation(self):
        # 70 inches × 2.5 = 175 lbs
        weight = calculate_weight(70, self.athletic)
        self.assertEqual(weight, 175)

    def test_weight_rounds_to_int(self):
        # 71 inches × 2.5 = 177.5 -> 177
        weight = calculate_weight(71, self.athletic)
        self.assertEqual(weight, 177)

    def test_weight_clamped_to_band_max(self):
        # 30 inches × 2.5 = 75, but tiny band max is 60
        weight = calculate_weight(30, self.athletic)
        self.assertEqual(weight, 60)

    def test_weight_clamped_to_band_min(self):
        # 150 inches × 2.5 = 375, but colossal band min is 400
        weight = calculate_weight(150, self.athletic)
        self.assertEqual(weight, 400)


class GetApparentHeightTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clear existing data to avoid conflicts with migration data
        from world.forms.models import HeightBand

        HeightBand.objects.all().delete()
        # Create height bands
        cls.average_band = HeightBandFactory(name="average", min_inches=67, max_inches=72)
        cls.tall_band = HeightBandFactory(name="tall", min_inches=73, max_inches=82)

        # Create horn trait with height modifier
        cls.horn_trait = FormTraitFactory(name="horn_type")
        cls.curved_horns = FormTraitOptionFactory(
            trait=cls.horn_trait,
            name="curved",
            height_modifier_inches=4,
        )
        cls.no_horns = FormTraitOptionFactory(
            trait=cls.horn_trait,
            name="none",
            height_modifier_inches=None,
        )

        # Create character with sheet
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def test_returns_base_height_without_modifiers(self):
        # Set up character with base height 70, no form traits
        self.sheet.true_height_inches = 70
        self.sheet.save()

        apparent, band = get_apparent_height(self.character)

        self.assertEqual(apparent, 70)
        self.assertEqual(band, self.average_band)

    def test_adds_height_modifier_from_form_trait(self):
        # Set up character with height 70 and curved horns (+4)
        self.sheet.true_height_inches = 70
        self.sheet.save()

        # Create form with curved horns
        form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(form=form, trait=self.horn_trait, option=self.curved_horns)
        CharacterFormStateFactory(character=self.character, active_form=form)

        apparent, band = get_apparent_height(self.character)

        self.assertEqual(apparent, 74)  # 70 + 4
        self.assertEqual(band, self.tall_band)

    def test_no_modifier_when_trait_has_none(self):
        self.sheet.true_height_inches = 70
        self.sheet.save()

        form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(form=form, trait=self.horn_trait, option=self.no_horns)
        CharacterFormStateFactory(character=self.character, active_form=form)

        apparent, _band = get_apparent_height(self.character)

        self.assertEqual(apparent, 70)


class GetApparentBuildTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clear existing data to avoid conflicts with migration data
        from world.forms.models import Build, HeightBand

        HeightBand.objects.all().delete()
        Build.objects.all().delete()
        cls.athletic = BuildFactory(name="athletic", display_name="Athletic")
        cls.colossal_band = HeightBandFactory(
            name="colossal", min_inches=145, max_inches=300, hide_build=True
        )
        cls.normal_band = HeightBandFactory(
            name="normal", min_inches=60, max_inches=80, hide_build=False
        )

        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def test_returns_character_build(self):
        self.sheet.build = self.athletic
        self.sheet.true_height_inches = 70
        self.sheet.save()

        build = get_apparent_build(self.character)

        self.assertEqual(build, self.athletic)

    def test_returns_none_when_band_hides_build(self):
        self.sheet.build = self.athletic
        self.sheet.true_height_inches = 150  # In colossal band
        self.sheet.save()

        build = get_apparent_build(self.character)

        self.assertIsNone(build)

    def test_returns_none_when_no_build_set(self):
        self.sheet.build = None
        self.sheet.true_height_inches = 70
        self.sheet.save()

        build = get_apparent_build(self.character)

        self.assertIsNone(build)


class CGHelperFunctionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clear existing data to avoid conflicts with migration data
        from world.forms.models import Build, HeightBand

        HeightBand.objects.all().delete()
        Build.objects.all().delete()
        cls.cg_band = HeightBandFactory(name="average", is_cg_selectable=True)
        cls.non_cg_band = HeightBandFactory(name="colossal", is_cg_selectable=False)
        cls.cg_build = BuildFactory(name="athletic", is_cg_selectable=True)
        cls.non_cg_build = BuildFactory(name="hulking", is_cg_selectable=False)

    def test_get_cg_height_bands_returns_only_selectable(self):
        bands = get_cg_height_bands()
        self.assertIn(self.cg_band, bands)
        self.assertNotIn(self.non_cg_band, bands)

    def test_get_cg_builds_returns_only_selectable(self):
        builds = get_cg_builds()
        self.assertIn(self.cg_build, builds)
        self.assertNotIn(self.non_cg_build, builds)
