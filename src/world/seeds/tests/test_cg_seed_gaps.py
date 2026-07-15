"""Tests for the character-creation seed data (FormTrait, Heritage, Pronouns, Family)."""

from django.test import TestCase

from world.character_sheets.models import Gender, Heritage, Pronouns
from world.forms.models import FormTrait, FormTraitOption, SpeciesFormTrait
from world.roster.models.families import Family
from world.seeds.character_creation import seed_character_creation_dev
from world.species.models import Species


class FormTraitSeedTests(TestCase):
    """Tests for FormTrait / FormTraitOption / SpeciesFormTrait seeding."""

    def test_form_traits_created(self):
        """Seed creates FormTrait rows for hair_color, eye_color, skin_tone."""
        seed_character_creation_dev()
        traits = FormTrait.objects.filter(name__in=["hair_color", "eye_color", "skin_tone"])
        self.assertEqual(traits.count(), 3)
        for trait in traits:
            self.assertTrue(trait.display_name)

    def test_form_trait_options_created(self):
        """Each FormTrait has multiple FormTraitOption rows."""
        seed_character_creation_dev()
        hair = FormTrait.objects.get(name="hair_color")
        self.assertGreaterEqual(hair.options.count(), 6)
        eye = FormTrait.objects.get(name="eye_color")
        self.assertGreaterEqual(eye.options.count(), 4)
        skin = FormTrait.objects.get(name="skin_tone")
        self.assertGreaterEqual(skin.options.count(), 4)

    def test_species_form_trait_links_human(self):
        """SpeciesFormTrait links Human to all seeded FormTraits with is_available_in_cg=True."""
        seed_character_creation_dev()
        human = Species.objects.get(name="Human")
        links = SpeciesFormTrait.objects.filter(species=human, is_available_in_cg=True)
        self.assertGreaterEqual(links.count(), 3)

    def test_idempotent(self):
        """Re-running doesn't create duplicates."""
        seed_character_creation_dev()
        seed_character_creation_dev()
        self.assertEqual(FormTrait.objects.filter(name="hair_color").count(), 1)
        self.assertEqual(FormTraitOption.objects.filter(trait__name="hair_color").count(), 7)
        human = Species.objects.get(name="Human")
        self.assertEqual(
            SpeciesFormTrait.objects.filter(species=human, trait__name="hair_color").count(),
            1,
        )


class HeritageSeedTests(TestCase):
    """Tests for Heritage seeding."""

    def test_heritages_created(self):
        """Seed creates Normal, Sleeper, and Misbegotten heritages."""
        seed_character_creation_dev()
        self.assertTrue(Heritage.objects.filter(name="Normal").exists())
        self.assertTrue(Heritage.objects.filter(name="Sleeper").exists())
        self.assertTrue(Heritage.objects.filter(name="Misbegotten").exists())

    def test_normal_heritage_family_known(self):
        """Normal heritage has family_known=True."""
        seed_character_creation_dev()
        normal = Heritage.objects.get(name="Normal")
        self.assertTrue(normal.family_known)
        self.assertFalse(normal.is_special)

    def test_special_heritages_family_unknown(self):
        """Sleeper and Misbegotten have family_known=False."""
        seed_character_creation_dev()
        sleeper = Heritage.objects.get(name="Sleeper")
        self.assertFalse(sleeper.family_known)
        self.assertTrue(sleeper.is_special)
        misbegotten = Heritage.objects.get(name="Misbegotten")
        self.assertFalse(misbegotten.family_known)
        self.assertTrue(misbegotten.is_special)

    def test_idempotent(self):
        seed_character_creation_dev()
        seed_character_creation_dev()
        self.assertEqual(Heritage.objects.filter(name="Normal").count(), 1)


class PronounsSeedTests(TestCase):
    """Tests for Pronouns seeding."""

    def test_pronouns_created(self):
        """Seed creates he/him, she/her, they/them."""
        seed_character_creation_dev()
        self.assertTrue(Pronouns.objects.filter(key="he_him").exists())
        self.assertTrue(Pronouns.objects.filter(key="she_her").exists())
        self.assertTrue(Pronouns.objects.filter(key="they_them").exists())

    def test_genders_created(self):
        """Seed creates male, female, non_binary, and unspecified."""
        seed_character_creation_dev()
        self.assertTrue(Gender.objects.filter(key="male").exists())
        self.assertTrue(Gender.objects.filter(key="female").exists())
        self.assertTrue(Gender.objects.filter(key="non_binary").exists())
        self.assertTrue(Gender.objects.filter(key="unspecified").exists())
        # unspecified is the default
        default = Gender.objects.get(key="unspecified")
        self.assertTrue(default.is_default)

    def test_pronoun_fields(self):
        """Pronoun fields are populated correctly."""
        seed_character_creation_dev()
        he = Pronouns.objects.get(key="he_him")
        self.assertEqual(he.subject, "he")
        self.assertEqual(he.object, "him")
        self.assertEqual(he.possessive, "his")

    def test_idempotent(self):
        seed_character_creation_dev()
        seed_character_creation_dev()
        self.assertEqual(Pronouns.objects.filter(key="he_him").count(), 1)


class CommonerFamilySeedTests(TestCase):
    """Tests for commoner Family seeding."""

    def test_families_created(self):
        """Seed creates at least one commoner family."""
        seed_character_creation_dev()
        families = Family.objects.filter(family_type=Family.FamilyType.COMMONER)
        self.assertGreaterEqual(families.count(), 1)

    def test_families_linked_to_realm(self):
        """Seeded families have origin_realm set."""
        seed_character_creation_dev()
        families = Family.objects.filter(family_type=Family.FamilyType.COMMONER)
        for family in families:
            self.assertIsNotNone(family.origin_realm)
            self.assertEqual(family.origin_realm.name, "Arx")

    def test_families_are_playable(self):
        """Seeded families are playable in CG."""
        seed_character_creation_dev()
        families = Family.objects.filter(family_type=Family.FamilyType.COMMONER)
        for family in families:
            self.assertTrue(family.is_playable)

    def test_idempotent(self):
        seed_character_creation_dev()
        seed_character_creation_dev()
        self.assertEqual(
            Family.objects.filter(name="The Vintners").count(),
            1,
        )
