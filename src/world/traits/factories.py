"""
Factory definitions for traits system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

import factory
from factory import django

from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    Trait,
    TraitCategory,
    TraitRankDescription,
    TraitType,
)


class TraitFactory(django.DjangoModelFactory):
    """Factory for creating Trait instances."""

    class Meta:
        model = Trait

    name = factory.Sequence(lambda n: f"trait_{n}")
    trait_type = TraitType.SKILL
    category = TraitCategory.GENERAL
    description = factory.Faker("sentence")
    is_public = True


class StatTraitFactory(TraitFactory):
    """Factory for creating stat traits."""

    trait_type = TraitType.STAT
    category = TraitCategory.PHYSICAL


class SkillTraitFactory(TraitFactory):
    """Factory for creating skill traits."""

    trait_type = TraitType.SKILL
    category = TraitCategory.GENERAL


class CharacterTraitValueFactory(django.DjangoModelFactory):
    """Factory for creating CharacterTraitValue instances."""

    class Meta:
        model = CharacterTraitValue

    trait = factory.SubFactory(TraitFactory)
    value = factory.Faker("random_int", min=1, max=100)


class PointConversionRangeFactory(django.DjangoModelFactory):
    """Factory for creating PointConversionRange instances."""

    class Meta:
        model = PointConversionRange

    trait_type = TraitType.SKILL
    min_value = 1
    max_value = 50
    points_per_level = 1


class CheckRankFactory(django.DjangoModelFactory):
    """Factory for creating CheckRank instances."""

    class Meta:
        model = CheckRank

    rank = factory.Sequence(lambda n: n)
    min_points = factory.LazyAttribute(lambda obj: obj.rank * 15)
    name = factory.Sequence(lambda n: f"Rank_{n}")
    description = factory.Faker("sentence")


class CheckOutcomeFactory(django.DjangoModelFactory):
    """Factory for creating CheckOutcome instances."""

    class Meta:
        model = CheckOutcome

    name = factory.Sequence(lambda n: f"Outcome_{n}")
    description = factory.Faker("sentence")
    success_level = factory.Faker("random_int", min=-5, max=5)
    display_template = factory.Faker("sentence")


class ResultChartFactory(django.DjangoModelFactory):
    """Factory for creating ResultChart instances."""

    class Meta:
        model = ResultChart

    rank_difference = factory.Sequence(lambda n: n - 5)  # Creates range -5 to +5
    name = factory.LazyAttribute(lambda obj: f"Chart_diff_{obj.rank_difference}")


class ResultChartOutcomeFactory(django.DjangoModelFactory):
    """Factory for creating ResultChartOutcome instances."""

    class Meta:
        model = ResultChartOutcome

    chart = factory.SubFactory(ResultChartFactory)
    outcome = factory.SubFactory(CheckOutcomeFactory)
    min_roll = 1
    max_roll = 100


class TraitRankDescriptionFactory(django.DjangoModelFactory):
    """Factory for creating TraitRankDescription instances."""

    class Meta:
        model = TraitRankDescription

    trait = factory.SubFactory(TraitFactory)
    value = factory.Faker("random_int", min=1, max=100)
    label = factory.Sequence(lambda n: f"Rank_Label_{n}")
    description = factory.Faker("sentence")


# Specialized factories for common test scenarios


class BasicSkillSetupFactory:
    """Factory for creating a basic skill testing setup."""

    @classmethod
    def create(cls, skill_name="test_skill", skill_value=30):
        """Create a complete skill testing setup."""
        # Create trait
        trait = SkillTraitFactory(name=skill_name)

        # Create conversion range
        conversion = PointConversionRangeFactory(
            trait_type=TraitType.SKILL, min_value=1, max_value=100, points_per_level=1
        )

        # Create basic ranks
        ranks = [
            CheckRankFactory(rank=0, min_points=0, name="Incompetent"),
            CheckRankFactory(rank=1, min_points=15, name="Novice"),
            CheckRankFactory(rank=2, min_points=30, name="Competent"),
            CheckRankFactory(rank=3, min_points=45, name="Skilled"),
        ]

        return {
            "trait": trait,
            "conversion": conversion,
            "ranks": ranks,
        }


class CheckSystemSetupFactory:
    """Factory for creating a complete check resolution system."""

    @classmethod
    def create(cls):
        """Create complete check system with charts and outcomes."""
        # Create outcomes
        outcomes = {
            "failure": CheckOutcomeFactory(name="Failure", success_level=-1),
            "partial": CheckOutcomeFactory(name="Partial Success", success_level=0),
            "success": CheckOutcomeFactory(name="Success", success_level=1),
            "critical": CheckOutcomeFactory(name="Critical Success", success_level=2),
        }

        # Create charts for different difficulties
        charts = {}
        for diff in [-2, -1, 0, 1, 2]:
            chart = ResultChartFactory(rank_difference=diff, name=f"Difficulty_{diff}")
            charts[diff] = chart

            # Add outcomes to chart based on difficulty
            if diff <= -1:  # Easy
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["failure"], min_roll=1, max_roll=20
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["success"], min_roll=21, max_roll=90
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["critical"], min_roll=91, max_roll=100
                )
            elif diff == 0:  # Even
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["failure"], min_roll=1, max_roll=40
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["partial"], min_roll=41, max_roll=60
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["success"], min_roll=61, max_roll=100
                )
            else:  # Hard (diff >= 1)
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["failure"], min_roll=1, max_roll=70
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["partial"], min_roll=71, max_roll=85
                )
                ResultChartOutcomeFactory(
                    chart=chart, outcome=outcomes["success"], min_roll=86, max_roll=100
                )

        return {
            "outcomes": outcomes,
            "charts": charts,
        }
