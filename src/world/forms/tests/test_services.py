from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition, remove_condition
from world.forms.factories import (
    AlternateSelfFactory,
    BuildFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormCombatProfileEffectFactory,
    FormCombatProfileFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    HeightBandFactory,
    PersonaTraitDescriptorFactory,
    SpeciesFormTraitFactory,
    TemporaryFormChangeFactory,
)
from world.forms.models import (
    ActiveAlternateSelf,
    AppearanceChangeLog,
    CharacterFormState,
    CharacterFormValue,
    DurationType,
    FormType,
)
from world.forms.services import (
    AlternateSelfActiveError,
    NonCosmeticTraitError,
    RevertBlockedError,
    assume_alternate_self,
    calculate_weight,
    change_appearance,
    create_true_form,
    get_apparent_build,
    get_apparent_form,
    get_apparent_height,
    get_cg_builds,
    get_cg_form_options,
    get_cg_height_bands,
    get_height_band,
    get_presented_appearance,
    reset_trait_to_natural,
    revert_alternate_self,
    revert_to_true_form,
    switch_form,
)
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.mechanics.constants import SOURCE_TYPE_FORM
from world.mechanics.models import CharacterModifier, ModifierSource
from world.scenes.factories import PersonaFactory
from world.species.factories import SpeciesFactory


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

        cls.hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.black = FormTraitOptionFactory(trait=cls.hair_trait, name="black", display_name="Black")
        cls.red = FormTraitOptionFactory(trait=cls.hair_trait, name="red", display_name="Red")
        cls.gray = FormTraitOptionFactory(trait=cls.hair_trait, name="gray", display_name="Gray")

        # Species has hair_color trait
        SpeciesFormTraitFactory(species=cls.species, trait=cls.hair_trait)

    def test_returns_all_options_for_species(self):
        options = get_cg_form_options(self.species)

        self.assertIn(self.hair_trait, options)
        trait_options = options[self.hair_trait]
        self.assertIn(self.black, trait_options)
        self.assertIn(self.red, trait_options)
        self.assertIn(self.gray, trait_options)

    def test_only_returns_cg_available_traits(self):
        # Create a non-CG trait
        eye_trait = FormTraitFactory(name="eye_color", display_name="Eye Color")
        FormTraitOptionFactory(trait=eye_trait, name="blue", display_name="Blue")
        SpeciesFormTraitFactory(species=self.species, trait=eye_trait, is_available_in_cg=False)

        options = get_cg_form_options(self.species)

        self.assertIn(self.hair_trait, options)
        self.assertNotIn(eye_trait, options)


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


class ChangeAppearanceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.sheet.primary_persona
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color", is_cosmetic=True)
        cls.brown = FormTraitOptionFactory(trait=cls.hair, name="brown", display_name="Brown")
        cls.blue = FormTraitOptionFactory(trait=cls.hair, name="blue", display_name="Blue")
        cls.height = FormTraitFactory(name="height", display_name="Height", is_cosmetic=False)
        cls.tall = FormTraitOptionFactory(trait=cls.height, name="tall", display_name="Tall")

    def setUp(self):
        self.form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(
            form=self.form, trait=self.hair, option=self.brown, natural_option=self.brown
        )

    def test_changes_current_preserves_natural_and_logs(self):
        change_appearance(
            self.character,
            self.hair,
            self.blue,
            persona=self.persona,
            descriptor="Robin's-egg",
            note="visited a stylist",
        )
        value = CharacterFormValue.objects.get(form=self.form, trait=self.hair)
        self.assertEqual(value.option, self.blue)
        self.assertEqual(value.natural_option, self.brown)
        log = AppearanceChangeLog.objects.get(form=self.form, trait=self.hair)
        self.assertEqual(log.from_option, self.brown)
        self.assertEqual(log.to_option, self.blue)
        self.assertEqual(log.to_text, "Robin's-egg")
        self.assertEqual(log.note, "visited a stylist")

    def test_rejects_non_cosmetic_trait(self):
        with self.assertRaises(NonCosmeticTraitError):
            change_appearance(self.character, self.height, self.tall, persona=self.persona)

    def test_clearing_descriptor_removes_it(self):
        change_appearance(
            self.character, self.hair, self.blue, persona=self.persona, descriptor="Crimson"
        )
        change_appearance(self.character, self.hair, self.blue, persona=self.persona, descriptor="")
        presented = {p.trait_name: p for p in get_presented_appearance(self.character)}
        self.assertEqual(presented["hair_color"].descriptor, "")
        self.assertEqual(presented["hair_color"].display, "Blue")

    def test_reset_to_natural(self):
        change_appearance(self.character, self.hair, self.blue, persona=self.persona)
        reset_trait_to_natural(self.character, self.hair, persona=self.persona)
        value = CharacterFormValue.objects.get(form=self.form, trait=self.hair)
        self.assertEqual(value.option, self.brown)


class GetPresentedAppearanceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.sheet.primary_persona
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color", is_cosmetic=True)
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red", display_name="Red")

    def setUp(self):
        self.form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=self.form, trait=self.hair, option=self.red)

    def test_descriptor_overlays_normalized(self):
        PersonaTraitDescriptorFactory(persona=self.persona, trait=self.hair, text="Crimson")
        presented = {p.trait_name: p for p in get_presented_appearance(self.character)}
        self.assertEqual(presented["hair_color"].normalized, "Red")
        self.assertEqual(presented["hair_color"].descriptor, "Crimson")
        self.assertEqual(presented["hair_color"].display, "Crimson")

    def test_blank_descriptor_falls_back_to_normalized(self):
        presented = {p.trait_name: p for p in get_presented_appearance(self.character)}
        self.assertEqual(presented["hair_color"].display, "Red")


class AssumeAlternateSelfTests(TestCase):
    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.true_form = CharacterFormFactory(
            character=self.character, name="True", form_type=FormType.TRUE
        )
        self.alt_form = CharacterFormFactory(
            character=self.character, name="Beast", form_type=FormType.ALTERNATE
        )
        self.form_state = CharacterFormStateFactory(
            character=self.character, active_form=self.true_form
        )
        self.persona = PersonaFactory(character_sheet=self.sheet)
        self.profile = FormCombatProfileFactory(form=self.alt_form)
        self.effect1 = FormCombatProfileEffectFactory(profile=self.profile)
        self.effect2 = FormCombatProfileEffectFactory(profile=self.profile)
        self.technique = TechniqueFactory()

    def test_assume_swaps_form_and_sets_return_anchors(self):
        alt_self = AlternateSelfFactory(character=self.sheet, form=self.alt_form)

        active = assume_alternate_self(self.sheet, alt_self)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.alt_form)
        self.assertEqual(active.return_form, self.true_form)
        self.assertEqual(active.alternate_self, alt_self)

    def test_assume_creates_stat_suite(self):
        alt_self = AlternateSelfFactory(character=self.sheet, combat_profile=self.profile)

        assume_alternate_self(self.sheet, alt_self)

        source = ModifierSource.objects.get(form_combat_profile=self.profile)
        self.assertEqual(source.source_type, SOURCE_TYPE_FORM)
        mods = list(CharacterModifier.objects.filter(source=source))
        self.assertEqual(len(mods), 2)

    def test_assume_swaps_persona(self):
        alt_self = AlternateSelfFactory(character=self.sheet, persona=self.persona)

        assume_alternate_self(self.sheet, alt_self)

        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.active_persona, self.persona)

    def test_assume_captures_return_persona(self):
        alt_self = AlternateSelfFactory(character=self.sheet, persona=self.persona)

        assume_alternate_self(self.sheet, alt_self)

        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        # return_persona captures the active persona at assume time; the sheet
        # was presenting its PRIMARY persona, so the stored anchor is None.
        self.assertIsNone(active.return_persona)
        self.sheet.refresh_from_db()
        # The alt-self's persona is now active.
        self.assertEqual(self.sheet.active_persona, self.persona)

    def test_assume_grants_techniques_tagged_to_source(self):
        alt_self = AlternateSelfFactory(character=self.sheet)
        alt_self.techniques.set([self.technique])

        assume_alternate_self(self.sheet, alt_self)

        ct = self.sheet.character_techniques.get(technique=self.technique)
        self.assertIsNotNone(ct.source)

    def test_assume_does_not_regrant_permanently_known_technique(self):
        alt_self = AlternateSelfFactory(character=self.sheet)
        alt_self.techniques.set([self.technique])
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique, source=None)

        assume_alternate_self(self.sheet, alt_self)

        cts = list(self.sheet.character_techniques.filter(technique=self.technique))
        self.assertEqual(len(cts), 1)
        self.assertIsNone(cts[0].source)

    def test_assume_is_idempotent_for_same_alt_self(self):
        alt_self = AlternateSelfFactory(character=self.sheet, form=self.alt_form)
        assume_alternate_self(self.sheet, alt_self)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        first_return_form = active.return_form

        assume_alternate_self(self.sheet, alt_self)

        active.refresh_from_db()
        self.assertEqual(active.return_form, first_return_form)

    def test_assume_raises_when_a_different_alt_self_is_active(self):
        # A different alt-self is already active — assuming a second would
        # orphan the first's grants. Enforce strictly-one-active.
        first = AlternateSelfFactory(character=self.sheet, combat_profile=self.profile)
        assume_alternate_self(self.sheet, first)
        first_sources = ModifierSource.objects.count()

        second_profile = FormCombatProfileFactory(form=self.alt_form)
        second = AlternateSelfFactory(character=self.sheet, combat_profile=second_profile)

        with self.assertRaises(AlternateSelfActiveError):
            assume_alternate_self(self.sheet, second)

        # No new grants were created; the first alt-self is still the active one.
        self.assertEqual(ModifierSource.objects.count(), first_sources)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.alternate_self, first)

    def test_assume_techniques_only_all_known_creates_no_orphan_source(self):
        # A techniques-only alt-self whose only technique is permanently known
        # grants nothing — no empty ModifierSource should leak each cycle.
        alt_self = AlternateSelfFactory(character=self.sheet)
        alt_self.techniques.set([self.technique])
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique, source=None)
        before = ModifierSource.objects.count()

        assume_alternate_self(self.sheet, alt_self)
        self.assertEqual(ModifierSource.objects.count(), before)

        revert_alternate_self(self.sheet)
        self.assertEqual(ModifierSource.objects.count(), before)
        # The permanently-known technique survives the revert untouched.
        ct = self.sheet.character_techniques.get(technique=self.technique)
        self.assertIsNone(ct.source)


class RevertAlternateSelfTests(TestCase):
    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.true_form = CharacterFormFactory(
            character=self.character, name="True", form_type=FormType.TRUE
        )
        self.alt_form = CharacterFormFactory(
            character=self.character, name="Beast", form_type=FormType.ALTERNATE
        )
        self.form_state = CharacterFormStateFactory(
            character=self.character, active_form=self.true_form
        )
        self.profile = FormCombatProfileFactory(form=self.alt_form)
        FormCombatProfileEffectFactory(profile=self.profile)
        self.technique = TechniqueFactory()

    def test_revert_restores_return_anchors_and_deletes_grants(self):
        alt_self = AlternateSelfFactory(
            character=self.sheet,
            form=self.alt_form,
            combat_profile=self.profile,
        )
        alt_self.techniques.set([self.technique])
        assume_alternate_self(self.sheet, alt_self)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.return_form, self.true_form)

        revert_alternate_self(self.sheet)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.true_form)
        self.assertFalse(ModifierSource.objects.filter(form_combat_profile=self.profile).exists())
        self.assertFalse(self.sheet.character_techniques.filter(technique=self.technique).exists())
        active.refresh_from_db()
        self.assertIsNone(active.alternate_self)
        self.assertIsNone(active.return_form)

    def test_revert_leaves_permanently_known_technique_intact(self):
        alt_self = AlternateSelfFactory(
            character=self.sheet,
            form=self.alt_form,
        )
        alt_self.techniques.set([self.technique])
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique, source=None)
        assume_alternate_self(self.sheet, alt_self)

        revert_alternate_self(self.sheet)

        self.assertTrue(self.sheet.character_techniques.filter(technique=self.technique).exists())
        ct = self.sheet.character_techniques.get(technique=self.technique)
        self.assertIsNone(ct.source)

    def test_revert_blocked_when_not_in_control(self):
        alt_self = AlternateSelfFactory(character=self.sheet, form=self.alt_form)
        assume_alternate_self(self.sheet, alt_self)

        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.sheet.character.conditions, "active", return_value=[fake_condition]):
            with self.assertRaises(RevertBlockedError):
                revert_alternate_self(self.sheet)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.alt_form)

    def test_assume_not_gated_by_in_control(self):
        alt_self = AlternateSelfFactory(character=self.sheet, form=self.alt_form)

        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.sheet.character.conditions, "active", return_value=[fake_condition]):
            active = assume_alternate_self(self.sheet, alt_self)

        self.assertEqual(active.alternate_self, alt_self)

    def test_revert_no_orphaned_source_for_persona_only_alt_self(self):
        persona = PersonaFactory(character_sheet=self.sheet)
        alt_self = AlternateSelfFactory(
            character=self.sheet,
            persona=persona,
            form=None,
            combat_profile=None,
        )
        before = ModifierSource.objects.count()

        assume_alternate_self(self.sheet, alt_self)
        self.assertEqual(ModifierSource.objects.count(), before)

        revert_alternate_self(self.sheet)
        self.assertEqual(ModifierSource.objects.count(), before)

    def test_revert_unblocked_after_alters_behavior_condition_removed(self):
        alt_self = AlternateSelfFactory(character=self.sheet, form=self.alt_form)
        assume_alternate_self(self.sheet, alt_self)

        category = ConditionCategoryFactory(alters_behavior=True)
        condition = ConditionTemplateFactory(category=category)
        apply_condition(self.sheet.character, condition)

        # ``in_control`` reads the character's ``CharacterConditionHandler``
        # cache, which ``apply_condition`` invalidated, so it re-derives fresh.
        self.assertIs(self.sheet.in_control, False)

        with self.assertRaises(RevertBlockedError):
            revert_alternate_self(self.sheet)

        remove_condition(self.sheet.character, condition)

        self.assertIs(self.sheet.in_control, True)

        revert_alternate_self(self.sheet)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.true_form)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertIsNone(active.alternate_self)
