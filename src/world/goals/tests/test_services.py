"""Tests for goal percentage services."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.models import (
    CharacterDistinction,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
)
from world.goals.factories import CharacterGoalFactory, GoalDomainFactory
from world.goals.services import (
    get_goal_bonus,
    get_goal_bonuses_breakdown,
    get_total_goal_points,
)
from world.mechanics.models import ModifierCategory, ModifierType
from world.mechanics.services import create_distinction_modifiers


class GetGoalBonusTest(TestCase):
    """Tests for get_goal_bonus service function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        # Create character with sheet
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        # Create goal percent modifier categories
        cls.goal_percent, _ = ModifierCategory.objects.get_or_create(
            name="goal_percent",
            defaults={"description": "Goal percentage modifiers", "display_order": 10},
        )
        cls.goal_points, _ = ModifierCategory.objects.get_or_create(
            name="goal_points",
            defaults={"description": "Goal points modifiers", "display_order": 11},
        )

        # Create percent modifier types
        cls.all_type, _ = ModifierType.objects.get_or_create(
            category=cls.goal_percent,
            name="all",
            defaults={"description": "All goals percent modifier"},
        )
        cls.needs_type, _ = ModifierType.objects.get_or_create(
            category=cls.goal_percent,
            name="needs",
            defaults={"description": "Needs goal percent modifier"},
        )
        cls.total_points_type, _ = ModifierType.objects.get_or_create(
            category=cls.goal_points,
            name="total_points",
            defaults={"description": "Total goal points modifier"},
        )

        # Create goal domains
        cls.needs_domain = GoalDomainFactory(name="Needs")
        cls.standing_domain = GoalDomainFactory(name="Standing")

        # Create personality category
        cls.personality_category, _ = DistinctionCategory.objects.get_or_create(
            slug="personality",
            defaults={"name": "Personality", "display_order": 3},
        )

        # Create Rapacious distinction
        cls.rapacious, _ = Distinction.objects.get_or_create(
            slug="rapacious",
            defaults={
                "name": "Rapacious",
                "category": cls.personality_category,
                "cost_per_rank": 5,
                "max_rank": 3,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.rapacious,
            target=cls.all_type,
            defaults={
                "value_per_rank": 50,
                "description": "+50% all goal modifiers",
            },
        )

        # Create Voracious distinction
        cls.voracious, _ = Distinction.objects.get_or_create(
            slug="voracious",
            defaults={
                "name": "Voracious",
                "category": cls.personality_category,
                "cost_per_rank": 5,
                "max_rank": 3,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.voracious,
            target=cls.needs_type,
            defaults={
                "scaling_values": [100, 200, 300],
                "description": "+100/200/300% Needs goal modifiers",
            },
        )

        # Create Ambitious distinction
        cls.ambitious, _ = Distinction.objects.get_or_create(
            slug="ambitious",
            defaults={
                "name": "Ambitious",
                "category": cls.personality_category,
                "cost_per_rank": 5,
                "max_rank": 1,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.ambitious,
            target=cls.total_points_type,
            defaults={
                "value_per_rank": 30,
                "description": "+30 goal points at character creation",
            },
        )

    def test_base_bonus_no_modifiers(self):
        """Base goal points returned without percentage modifiers."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )

        bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert bonus == 10

    def test_zero_points_returns_zero(self):
        """Zero base points returns zero regardless of multipliers."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=0,
        )

        bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert bonus == 0

    def test_missing_goal_returns_zero(self):
        """Missing CharacterGoal returns zero."""
        bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert bonus == 0

    def test_rapacious_applies_all_percent(self):
        """Rapacious +50% applies to all goal bonuses."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )
        CharacterGoalFactory(
            character=self.character,
            domain=self.standing_domain,
            points=8,
        )

        # Grant Rapacious distinction
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.rapacious,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # 10 * 1.5 = 15
        needs_bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert needs_bonus == 15

        # 8 * 1.5 = 12
        standing_bonus = get_goal_bonus(self.character_sheet, "Standing")
        assert standing_bonus == 12

    def test_voracious_applies_needs_only(self):
        """Voracious applies only to Needs goals."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )
        CharacterGoalFactory(
            character=self.character,
            domain=self.standing_domain,
            points=8,
        )

        # Grant Voracious at rank 1 (+100%)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.voracious,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Needs: 10 * 2.0 = 20
        needs_bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert needs_bonus == 20

        # Standing: no modifier, stays 8
        standing_bonus = get_goal_bonus(self.character_sheet, "Standing")
        assert standing_bonus == 8

    def test_voracious_rank_scaling(self):
        """Voracious scales with rank: +100/200/300%."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )

        # Grant Voracious at rank 3 (+300%)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.voracious,
            rank=3,
        )
        create_distinction_modifiers(char_distinction)

        # 10 * 4.0 = 40
        bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert bonus == 40

    def test_combined_all_and_domain_modifiers(self):
        """All percent and domain percent stack additively."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )

        # Grant both distinctions
        rapacious_cd = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.rapacious,
            rank=1,
        )
        create_distinction_modifiers(rapacious_cd)

        voracious_cd = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.voracious,
            rank=1,
        )
        create_distinction_modifiers(voracious_cd)

        # Rapacious: +50%, Voracious: +100% = +150% total
        # 10 * 2.5 = 25
        bonus = get_goal_bonus(self.character_sheet, "Needs")
        assert bonus == 25


class GetTotalGoalPointsTest(TestCase):
    """Tests for get_total_goal_points service function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        # Create goal points modifier category and type
        cls.goal_points, _ = ModifierCategory.objects.get_or_create(
            name="goal_points",
            defaults={"description": "Goal points modifiers", "display_order": 11},
        )
        cls.total_points_type, _ = ModifierType.objects.get_or_create(
            category=cls.goal_points,
            name="total_points",
            defaults={"description": "Total goal points modifier"},
        )

        # Create personality category and Ambitious distinction
        cls.personality_category, _ = DistinctionCategory.objects.get_or_create(
            slug="personality",
            defaults={"name": "Personality", "display_order": 3},
        )
        cls.ambitious, _ = Distinction.objects.get_or_create(
            slug="ambitious",
            defaults={
                "name": "Ambitious",
                "category": cls.personality_category,
                "cost_per_rank": 5,
                "max_rank": 1,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.ambitious,
            target=cls.total_points_type,
            defaults={
                "value_per_rank": 30,
                "description": "+30 goal points at character creation",
            },
        )

    def test_base_points_no_modifiers(self):
        """Base 30 points without modifiers."""
        total = get_total_goal_points(self.character_sheet)
        assert total == 30

    def test_ambitious_adds_points(self):
        """Ambitious adds 30 goal points."""
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.ambitious,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        total = get_total_goal_points(self.character_sheet)
        assert total == 60  # 30 base + 30 from Ambitious


class GetGoalBonusesBreakdownTest(TestCase):
    """Tests for get_goal_bonuses_breakdown service function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        # Create goal percent modifier category
        cls.goal_percent, _ = ModifierCategory.objects.get_or_create(
            name="goal_percent",
            defaults={"description": "Goal percentage modifiers", "display_order": 10},
        )
        cls.all_type, _ = ModifierType.objects.get_or_create(
            category=cls.goal_percent,
            name="all",
            defaults={"description": "All goals percent modifier"},
        )

        # Create goal domain
        cls.needs_domain = GoalDomainFactory(name="Needs")

        # Create Rapacious distinction
        cls.personality_category, _ = DistinctionCategory.objects.get_or_create(
            slug="personality",
            defaults={"name": "Personality", "display_order": 3},
        )
        cls.rapacious, _ = Distinction.objects.get_or_create(
            slug="rapacious",
            defaults={
                "name": "Rapacious",
                "category": cls.personality_category,
                "cost_per_rank": 5,
                "max_rank": 3,
            },
        )
        DistinctionEffect.objects.get_or_create(
            distinction=cls.rapacious,
            target=cls.all_type,
            defaults={
                "value_per_rank": 50,
                "description": "+50% all goal modifiers",
            },
        )

    def test_breakdown_includes_all_domains(self):
        """Breakdown includes all goal domains."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )

        breakdown = get_goal_bonuses_breakdown(self.character_sheet)

        assert "Needs" in breakdown
        assert breakdown["Needs"]["base_points"] == 10
        assert breakdown["Needs"]["percent_modifier"] == 0
        assert breakdown["Needs"]["final_bonus"] == 10

    def test_breakdown_shows_percent_modifiers(self):
        """Breakdown shows percentage modifiers."""
        CharacterGoalFactory(
            character=self.character,
            domain=self.needs_domain,
            points=10,
        )

        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.rapacious,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        breakdown = get_goal_bonuses_breakdown(self.character_sheet)

        assert breakdown["Needs"]["base_points"] == 10
        assert breakdown["Needs"]["percent_modifier"] == 50
        assert breakdown["Needs"]["final_bonus"] == 15
