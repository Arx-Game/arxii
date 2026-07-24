"""Social-check seed — stat + skill + specialization compositions (#1688 slice 2)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.models import CheckType, CheckTypeSpecialization, CheckTypeTrait
from world.checks.services import perform_check
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Skill, Specialization
from world.traits.models import CharacterTraitValue, Trait, TraitType


class SocialCheckSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_social_check_content()

    def test_seeds_parent_skills(self):
        for name in ("Persuasion", "Performance"):
            assert Skill.objects.filter(trait__name=name).exists()

    def test_seeds_specializations_under_their_parents(self):
        persuasion_specs = set(
            Specialization.objects.filter(parent_skill__trait__name="Persuasion").values_list(
                "name", flat=True
            )
        )
        assert {"Seduction", "Manipulation", "Intimidation", "Gossip", "Propaganda"} <= (
            persuasion_specs
        )
        performance_specs = set(
            Specialization.objects.filter(parent_skill__trait__name="Performance").values_list(
                "name", flat=True
            )
        )
        assert {"Singing", "Dancing", "Poetry", "Oratory"} <= performance_specs

    def test_seduction_check_is_stat_skill_spec(self):
        seduction = CheckType.objects.get(name="Seduction")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=seduction).values_list(
                "trait__name", flat=True
            )
        )
        assert trait_names == {"charm", "Persuasion"}
        spec_names = set(
            CheckTypeSpecialization.objects.filter(check_type=seduction).values_list(
                "specialization__name", flat=True
            )
        )
        assert spec_names == {"Seduction"}

    def test_intimidation_rolls_presence_not_charm(self):
        intimidation = CheckType.objects.get(name="Intimidation")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=intimidation).values_list(
                "trait__name", flat=True
            )
        )
        assert trait_names == {"presence", "Persuasion"}

    def test_persuasion_base_has_no_specialization(self):
        persuasion = CheckType.objects.get(name="Persuasion")
        assert not CheckTypeSpecialization.objects.filter(check_type=persuasion).exists()

    def test_reseed_is_authoritative(self):
        # A stray placeholder trait must be wiped by a reseed — the seed owns the composition.
        seduction = CheckType.objects.get(name="Seduction")
        stray = Trait.objects.create(name="stray_placeholder_stat", trait_type=TraitType.STAT)
        CheckTypeTrait.objects.create(check_type=seduction, trait=stray)
        seed_social_check_content()
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=seduction).values_list(
                "trait__name", flat=True
            )
        )
        assert trait_names == {"charm", "Persuasion"}

    def test_owned_seduction_spec_contributes_to_the_check(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        CharacterTraitValue.objects.create(
            character=sheet, trait=Trait.objects.get(name="charm"), value=30
        )
        seduction = CheckType.objects.get(name="Seduction")
        base = perform_check(character, seduction, target_difficulty=0)
        spec = Specialization.objects.get(name="Seduction", parent_skill__trait__name="Persuasion")
        CharacterSpecializationValueFactory(character=sheet, specialization=spec, value=30)
        with_spec = perform_check(character, seduction, target_difficulty=0)
        assert with_spec.specialization_points > base.specialization_points
