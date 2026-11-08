from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.traits.models import Trait, TraitCategory, TraitType


class TraitTypeTests(TestCase):
    def test_modifier_target_exists(self):
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

    def test_a_skill_is_a_skill_type_trait(self):
        """Skill is a proxy of Trait (#5008): saving one makes a SKILL trait."""
        from world.skills.models import Skill

        skill = Skill.objects.create(name="Swordplay", category=TraitCategory.COMBAT)
        assert Trait.objects.get(pk=skill.pk).trait_type == TraitType.SKILL
        assert str(skill) == "Swordplay"

    def test_skill_objects_sees_only_skills(self):
        """A cached stat never comes back through Skill, by pk or natural key."""
        from world.skills.models import Skill

        stat = Trait.objects.create(
            name="strength_test", trait_type=TraitType.STAT, category=TraitCategory.PHYSICAL
        )
        assert Skill.objects.get(pk=self.trait.pk).pk == self.trait.pk
        assert not Skill.objects.filter(pk=stat.pk).exists()
        with self.assertRaises(Skill.DoesNotExist):
            Skill.objects.get(pk=stat.pk)
        with self.assertRaises(Skill.DoesNotExist):
            Skill.objects.get_by_natural_key("strength_test")
        assert Trait.get_by_name("strength_test") == stat


class SpecializationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.skills.models import Skill

        cls.trait = Trait.objects.create(
            name="Melee Combat",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )
        cls.skill = Skill.objects.get(pk=cls.trait.pk)

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


class CharacterSpecializationValueModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = Trait.objects.create(
            name="Melee Combat",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )

    def setUp(self):
        from world.skills.models import (
            CharacterSpecializationValue,
            Skill,
            Specialization,
        )

        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSpecializationValue.flush_instance_cache()
        Skill.flush_instance_cache()
        Specialization.flush_instance_cache()

        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.skill = Skill.objects.get(pk=self.trait.pk)
        self.spec = Specialization.objects.get_or_create(
            name="Swords",
            parent_skill=self.skill,
        )[0]

    def test_character_specialization_value_creation(self):
        """CharacterSpecializationValue should store value with development tracking."""
        from world.skills.models import CharacterSpecializationValue

        csw = CharacterSpecializationValue.objects.create(
            character=self.sheet,
            specialization=self.spec,
            value=10,
        )
        assert csw.value == 10
        assert csw.development_points == 0
        # No rust_points - specializations are immune

    def test_character_specialization_display_value(self):
        """Specializations display their true stored value, like skills (ADR-0193)."""
        from world.skills.models import CharacterSpecializationValue

        csw = CharacterSpecializationValue.objects.create(
            character=self.sheet,
            specialization=self.spec,
            value=15,
        )
        assert csw.display_value == 15


class SkillPointBudgetModelTests(TestCase):
    def test_budget_defaults(self):
        """SkillPointBudget should have sensible defaults."""
        from world.skills.models import SkillPointBudget

        budget = SkillPointBudget.objects.create()
        assert budget.path_points == 50
        assert budget.free_points == 60
        assert budget.points_per_tier == 10
        assert budget.specialization_unlock_threshold == 30
        assert budget.max_skill_value == 30
        assert budget.max_specialization_value == 30

    def test_get_active_budget_creates_if_missing(self):
        """get_active_budget should create budget if none exists."""
        from world.skills.models import SkillPointBudget

        SkillPointBudget.objects.all().delete()
        budget = SkillPointBudget.get_active_budget()
        assert budget is not None
        assert budget.pk is not None

    def test_get_active_budget_returns_existing(self):
        """get_active_budget should return existing budget."""
        from world.skills.models import SkillPointBudget

        # Use pk=1 since get_active_budget uses get_or_create(pk=1)
        existing = SkillPointBudget.objects.create(pk=1, path_points=60)
        budget = SkillPointBudget.get_active_budget()
        assert budget.pk == existing.pk
        assert budget.path_points == 60

    def test_total_points_property(self):
        """total_points should sum path_points and free_points."""
        from world.skills.models import SkillPointBudget

        budget = SkillPointBudget.objects.create(path_points=50, free_points=60)
        assert budget.total_points == 110


class PathSkillSuggestionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.classes.models import Path, PathStage

        cls.trait = Trait.objects.create(
            name="Defense",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )
        cls.character_path = Path.objects.create(
            name="Fighter Path",
            description="A martial warrior path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def setUp(self):
        from world.skills.models import Skill

        self.skill = Skill.objects.get(pk=self.trait.pk)

    def test_path_skill_suggestion_creation(self):
        """PathSkillSuggestion should link path to suggested skill value."""
        from world.skills.models import PathSkillSuggestion

        suggestion = PathSkillSuggestion.objects.create(
            character_path=self.character_path,
            skill=self.skill,
            suggested_value=20,
        )
        assert suggestion.character_path.name == "Fighter Path"
        assert suggestion.skill.name == "Defense"
        assert suggestion.suggested_value == 20

    def test_path_skill_suggestion_unique(self):
        """Path can only have one suggestion per skill."""
        from django.db import IntegrityError

        from world.skills.models import PathSkillSuggestion

        PathSkillSuggestion.objects.create(
            character_path=self.character_path,
            skill=self.skill,
            suggested_value=10,
        )
        with self.assertRaises(IntegrityError):
            PathSkillSuggestion.objects.create(
                character_path=self.character_path,
                skill=self.skill,
                suggested_value=20,
            )


class FactoryTests(TestCase):
    """Tests for skills factories."""

    def test_skill_factory(self):
        """SkillFactory should create valid Skill."""
        from world.skills.factories import SkillFactory

        skill = SkillFactory()
        assert skill.pk is not None
        assert skill.trait_type == TraitType.SKILL

    def test_specialization_factory(self):
        """SpecializationFactory should create valid Specialization."""
        from world.skills.factories import SpecializationFactory

        spec = SpecializationFactory()
        assert spec.pk is not None
        assert spec.parent_skill is not None

    def test_skill_rating_factory(self):
        """SkillRatingFactory makes the skill trait's CharacterTraitValue (#5010)."""
        from world.skills.factories import SkillRatingFactory

        rating = SkillRatingFactory()
        assert rating.pk is not None
        assert rating.trait.trait_type == TraitType.SKILL

    def test_character_specialization_value_factory(self):
        """CharacterSpecializationValueFactory should create valid value."""
        from world.skills.factories import CharacterSpecializationValueFactory

        csw = CharacterSpecializationValueFactory()
        assert csw.pk is not None
        assert csw.character is not None
        assert csw.specialization is not None

    def test_skill_point_budget_factory(self):
        """SkillPointBudgetFactory should create valid SkillPointBudget."""
        from world.skills.factories import SkillPointBudgetFactory

        budget = SkillPointBudgetFactory()
        assert budget.pk is not None
        assert budget.path_points == 50
        assert budget.free_points == 60

    def test_path_skill_suggestion_factory(self):
        """PathSkillSuggestionFactory should create valid PathSkillSuggestion."""
        from world.skills.factories import PathSkillSuggestionFactory

        suggestion = PathSkillSuggestionFactory()
        assert suggestion.pk is not None
        assert suggestion.character_path is not None
        assert suggestion.skill is not None
