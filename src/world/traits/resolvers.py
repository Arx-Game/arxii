"""
Check resolution system for the traits system.

Handles the trait values → points → ranks → charts → outcomes flow
for resolving trait-based checks and contests.
"""

import random
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.traits.models import CheckOutcome, CheckRank, ResultChart, ResultChartOutcome
from world.traits.types import CheckResult


class CheckResolver:
    """
    Handles check resolution using the Arx II check system.

    Implements the trait values → points → ranks → charts → outcomes flow.
    """

    @classmethod
    def resolve_check(
        cls,
        roller: "ObjectDB",
        roller_traits: list[str],
        target_points: int = 0,
        difficulty_modifier: int = 0,
    ) -> CheckResult:
        """
        Resolve a check using the full Arx II system with trait handler caching.

        Args:
            roller: Character making the check
            roller_traits: List of trait names to use for the check
            target_points: Target difficulty in points (0 for unopposed)
            difficulty_modifier: Modifier to apply to rank difference

        Returns:
            CheckResult containing complete check results with proper typing
        """
        # Use the character's trait handler for efficient cached lookups
        handler = cast(Any, roller).traits

        # Calculate roller's total points using cached values
        roller_points = handler.calculate_check_points(roller_traits)

        # Get ranks for roller and target
        roller_rank = CheckRank.get_rank_for_points(roller_points)
        target_rank = CheckRank.get_rank_for_points(target_points)

        # Calculate rank difference
        rank_difference = 0
        if roller_rank and target_rank:
            rank_difference = roller_rank.rank - target_rank.rank
        elif roller_rank:
            rank_difference = roller_rank.rank

        # Apply difficulty modifier
        rank_difference += difficulty_modifier

        # Get appropriate result chart
        chart = ResultChart.get_chart_for_difference(rank_difference)

        # Perform the roll and determine outcome
        roll = random.randint(1, 100)
        outcome = None
        if chart:
            outcome = cls._get_outcome_for_roll(chart, roll)

        return CheckResult(
            roller=roller,
            roller_traits=roller_traits,
            roller_points=roller_points,
            roller_rank=roller_rank,
            target_points=target_points,
            target_rank=target_rank,
            rank_difference=rank_difference,
            chart=chart,
            roll=roll,
            outcome=outcome,
        )

    @classmethod
    def _get_outcome_for_roll(
        cls,
        chart: ResultChart,
        roll: int,
    ) -> CheckOutcome | None:
        """
        Get the outcome for a specific roll on a result chart.

        Args:
            chart: The result chart to use
            roll: The dice roll (1-100)

        Returns:
            CheckOutcome that matches the roll, or None if no match
        """
        try:
            chart_outcome = ResultChartOutcome.objects.get(
                chart=chart,
                min_roll__lte=roll,
                max_roll__gte=roll,
            )
            return cast(CheckOutcome, chart_outcome.outcome)
        except ObjectDoesNotExist:
            return None


def perform_check(
    character: "ObjectDB",
    trait_names: list[str],
    target_difficulty: int = 0,
    difficulty_modifier: int = 0,
) -> CheckResult:
    """
    Convenience function to perform a trait check with caching.

    Args:
        character: Character making the check
        trait_names: List of trait names to use
        target_difficulty: Target difficulty in points
        difficulty_modifier: Modifier to rank difference

    Returns:
        CheckResult with complete check results and proper typing
    """
    return CheckResolver.resolve_check(
        character,
        trait_names,
        target_difficulty,
        difficulty_modifier,
    )
