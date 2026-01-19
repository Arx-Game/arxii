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
        cls.trait = Trait.objects.create(
            name="Persuasion",
            trait_type=TraitType.SKILL,
            category=TraitCategory.SOCIAL,
        )

    def setUp(self):
        from evennia_extensions.factories import CharacterFactory
        from world.skills.models import CharacterSkillValue, Skill

        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSkillValue.flush_instance_cache()
        Skill.flush_instance_cache()

        self.character = CharacterFactory()
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


class CharacterSpecializationValueModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = Trait.objects.create(
            name="Melee Combat",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )

    def setUp(self):
        from evennia_extensions.factories import CharacterFactory
        from world.skills.models import (
            CharacterSpecializationValue,
            Skill,
            Specialization,
        )

        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSpecializationValue.flush_instance_cache()
        Skill.flush_instance_cache()
        Specialization.flush_instance_cache()

        self.character = CharacterFactory()
        self.skill = Skill.objects.get_or_create(trait=self.trait)[0]
        self.spec = Specialization.objects.get_or_create(
            name="Swords",
            parent_skill=self.skill,
        )[0]

    def test_character_specialization_value_creation(self):
        """CharacterSpecializationValue should store value with development tracking."""
        from world.skills.models import CharacterSpecializationValue

        csw = CharacterSpecializationValue.objects.create(
            character=self.character,
            specialization=self.spec,
            value=10,
        )
        assert csw.value == 10
        assert csw.development_points == 0
        # No rust_points - specializations are immune

    def test_character_specialization_display_value(self):
        """Display value should be value / 10."""
        from world.skills.models import CharacterSpecializationValue

        csw = CharacterSpecializationValue.objects.create(
            character=self.character,
            specialization=self.spec,
            value=15,
        )
        assert csw.display_value == 1.5


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
        from world.classes.models import CharacterClass

        cls.trait = Trait.objects.create(
            name="Defense",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )
        cls.character_class = CharacterClass.objects.create(
            name="Fighter",
            description="A martial warrior",
        )

    def setUp(self):
        from world.skills.models import Skill

        self.skill = Skill.objects.get_or_create(trait=self.trait)[0]

    def test_path_skill_suggestion_creation(self):
        """PathSkillSuggestion should link path to suggested skill value."""
        from world.skills.models import PathSkillSuggestion

        suggestion = PathSkillSuggestion.objects.create(
            character_class=self.character_class,
            skill=self.skill,
            suggested_value=20,
        )
        assert suggestion.character_class.name == "Fighter"
        assert suggestion.skill.name == "Defense"
        assert suggestion.suggested_value == 20

    def test_path_skill_suggestion_unique(self):
        """Path can only have one suggestion per skill."""
        from django.db import IntegrityError

        from world.skills.models import PathSkillSuggestion

        PathSkillSuggestion.objects.create(
            character_class=self.character_class,
            skill=self.skill,
            suggested_value=10,
        )
        with self.assertRaises(IntegrityError):
            PathSkillSuggestion.objects.create(
                character_class=self.character_class,
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
        assert skill.trait.trait_type == TraitType.SKILL

    def test_specialization_factory(self):
        """SpecializationFactory should create valid Specialization."""
        from world.skills.factories import SpecializationFactory

        spec = SpecializationFactory()
        assert spec.pk is not None
        assert spec.parent_skill is not None

    def test_character_skill_value_factory(self):
        """CharacterSkillValueFactory should create valid CharacterSkillValue."""
        from world.skills.factories import CharacterSkillValueFactory

        csv = CharacterSkillValueFactory()
        assert csv.pk is not None
        assert csv.character is not None
        assert csv.skill is not None

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
        assert suggestion.character_class is not None
        assert suggestion.skill is not None
