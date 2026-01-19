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
