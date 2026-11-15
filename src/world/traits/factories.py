"""
Factory definitions for traits system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

import factory
import factory.django as factory_django

from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierLevelBaseline
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


class TraitFactory(factory_django.DjangoModelFactory):
    """Factory for creating Trait instances."""

    class Meta:
        model = Trait
        django_get_or_create = ("name",)

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


class CharacterTraitValueFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterTraitValue instances."""

    class Meta:
        model = CharacterTraitValue

    trait = factory.SubFactory(TraitFactory)
    value = factory.Faker("random_int", min=1, max=100)


class PointConversionRangeFactory(factory_django.DjangoModelFactory):
    """Factory for creating PointConversionRange instances."""

    class Meta:
        model = PointConversionRange

    trait_type = TraitType.SKILL
    min_value = 1
    max_value = 50
    points_per_level = 1


def ensure_check_rank(rank: int, min_points: int, name: str) -> CheckRank:
    """A ``CheckRank`` whose ladder threshold is ``min_points`` (#5093).

    A rank's threshold is the CHECK lane's level-``rank`` baseline, so this writes that
    baseline row too (rank 0 starts at 0 and needs none). Create-if-missing on both rows.
    """
    if rank > 0:
        ModifierLevelBaseline.objects.get_or_create(
            lane=ModifierLane.CHECK, level=rank, defaults={"baseline": min_points}
        )
    return CheckRank.objects.get_or_create(rank=rank, defaults={"name": name})[0]


class CheckRankFactory(factory_django.DjangoModelFactory):
    """Factory for creating CheckRank instances.

    ``min_points`` is not a column: it is the rank's threshold, written as the CHECK lane's
    level-``rank`` baseline (rank 0 needs none).
    """

    class Meta:
        model = CheckRank

    rank = factory.Sequence(lambda n: n)
    min_points = factory.LazyAttribute(lambda obj: obj.rank * 15)
    name = factory.Sequence(lambda n: f"Rank_{n}")
    description = factory.Faker("sentence")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        min_points = kwargs.pop("min_points")
        if kwargs["rank"] > 0:
            ModifierLevelBaseline.objects.update_or_create(
                lane=ModifierLane.CHECK, level=kwargs["rank"], defaults={"baseline": min_points}
            )
        return super()._create(model_class, *args, **kwargs)


class CheckOutcomeFactory(factory_django.DjangoModelFactory):
    """Factory for creating CheckOutcome instances."""

    class Meta:
        model = CheckOutcome
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Outcome_{n}")
    description = factory.Faker("sentence")
    success_level = factory.Faker("random_int", min=-5, max=5)
    display_template = factory.Faker("sentence")


class ResultChartFactory(factory_django.DjangoModelFactory):
    """Factory for creating ResultChart instances."""

    class Meta:
        model = ResultChart

    rank_difference = factory.Sequence(lambda n: n - 5)  # Creates range -5 to +5
    name = factory.LazyAttribute(lambda obj: f"Chart_diff_{obj.rank_difference}")


class ResultChartOutcomeFactory(factory_django.DjangoModelFactory):
    """Factory for creating ResultChartOutcome instances."""

    class Meta:
        model = ResultChartOutcome

    chart = factory.SubFactory(ResultChartFactory)
    outcome = factory.SubFactory(CheckOutcomeFactory)
    min_roll = 1
    max_roll = 100


class TraitRankDescriptionFactory(factory_django.DjangoModelFactory):
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
            trait_type=TraitType.SKILL,
            min_value=1,
            max_value=100,
            points_per_level=1,
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

            # Add outcomes to chart based on difficulty. rank_difference is
            # roller_rank - target_rank, so a negative diff means the roller is
            # weaker and must get the hard bands; a positive diff means the
            # roller is stronger and must get the easy bands (#2707).
            if diff <= -1:  # Hard
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["failure"],
                    min_roll=1,
                    max_roll=70,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["partial"],
                    min_roll=71,
                    max_roll=85,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["success"],
                    min_roll=86,
                    max_roll=100,
                )
            elif diff == 0:  # Even
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["failure"],
                    min_roll=1,
                    max_roll=40,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["partial"],
                    min_roll=41,
                    max_roll=60,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["success"],
                    min_roll=61,
                    max_roll=100,
                )
            else:  # Easy (diff >= 1)
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["failure"],
                    min_roll=1,
                    max_roll=20,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["success"],
                    min_roll=21,
                    max_roll=90,
                )
                ResultChartOutcomeFactory(
                    chart=chart,
                    outcome=outcomes["critical"],
                    min_roll=91,
                    max_roll=100,
                )

        return {
            "outcomes": outcomes,
            "charts": charts,
        }
