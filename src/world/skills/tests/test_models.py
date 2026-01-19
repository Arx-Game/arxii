from django.test import TestCase

from world.traits.models import Trait, TraitCategory, TraitType


class TraitTypeTests(TestCase):
    def test_modifier_type_exists(self):
        """TraitType should have MODIFIER option for contextual bonuses."""
        assert TraitType.MODIFIER == "modifier"
        assert TraitType.MODIFIER.label == "Modifier"


class SkillModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = Trait.objects.create(
            name="Melee Combat",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
            description="Close-quarters fighting ability",
        )

    def test_skill_creation(self):
        """Skill should link to a Trait with type SKILL."""
        from world.skills.models import Skill

        skill = Skill.objects.create(
            trait=self.trait,
            tooltip="Fighting with melee weapons",
            display_order=1,
        )
        assert skill.trait.name == "Melee Combat"
        assert skill.tooltip == "Fighting with melee weapons"
        assert skill.is_active is True

    def test_skill_name_property(self):
        """Skill should expose name from linked trait."""
        from world.skills.models import Skill

        skill = Skill.objects.create(trait=self.trait)
        assert skill.name == "Melee Combat"

    def test_skill_category_property(self):
        """Skill should expose category from linked trait."""
        from world.skills.models import Skill

        skill = Skill.objects.create(trait=self.trait)
        assert skill.category == TraitCategory.COMBAT


class SpecializationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.skills.models import Skill

        cls.trait = Trait.objects.create(
            name="Melee Combat",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )
        cls.skill = Skill.objects.create(trait=cls.trait)

    def test_specialization_creation(self):
        """Specialization should link to a parent skill."""
        from world.skills.models import Specialization

        spec = Specialization.objects.create(
            name="Swords",
            parent_skill=self.skill,
            description="Fighting with bladed weapons",
            tooltip="Expertise with swords and similar weapons",
        )
        assert spec.name == "Swords"
        assert spec.parent_skill == self.skill
        assert spec.is_active is True

    def test_specialization_parent_name(self):
        """Specialization should expose parent skill name."""
        from world.skills.models import Specialization

        spec = Specialization.objects.create(
            name="Swords",
            parent_skill=self.skill,
        )
        assert spec.parent_name == "Melee Combat"


class CharacterSkillValueModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from evennia.utils.create import create_object

        cls.trait = Trait.objects.create(
            name="Persuasion",
            trait_type=TraitType.SKILL,
            category=TraitCategory.SOCIAL,
        )
        cls.character = create_object(
            typeclass="typeclasses.characters.Character",
            key="TestChar",
        )

    def setUp(self):
        from world.skills.models import Skill

        self.skill = Skill.objects.get_or_create(trait=self.trait)[0]

    def test_character_skill_value_creation(self):
        """CharacterSkillValue should store skill value with progression tracking."""
        from world.skills.models import CharacterSkillValue

        csv = CharacterSkillValue.objects.create(
            character=self.character,
            skill=self.skill,
            value=20,
        )
        assert csv.value == 20
        assert csv.development_points == 0
        assert csv.rust_points == 0

    def test_character_skill_display_value(self):
        """Display value should be value / 10."""
        from world.skills.models import CharacterSkillValue

        csv = CharacterSkillValue.objects.create(
            character=self.character,
            skill=self.skill,
            value=25,
        )
        assert csv.display_value == 2.5

    def test_character_skill_unique_constraint(self):
        """Character can only have one value per skill."""
        from django.db import IntegrityError

        from world.skills.models import CharacterSkillValue

        CharacterSkillValue.objects.create(
            character=self.character,
            skill=self.skill,
            value=10,
        )
        with self.assertRaises(IntegrityError):
            CharacterSkillValue.objects.create(
                character=self.character,
                skill=self.skill,
                value=20,
            )
