"""Check resolution service functions."""

import random
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist

from world.checks.types import CheckResult, OutcomeSummary
from world.classes.models import CharacterClassLevel, PathAspect
from world.progression.models import CharacterPathHistory
from world.traits.models import (
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    Trait,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.traits.handlers import TraitHandler


def perform_check(
    character: "ObjectDB",
    check_type: "CheckType",
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
) -> CheckResult:
    """
    Main check resolution function.

    1. Calculate weighted trait points using TraitHandler
    2. Calculate aspect bonus from path
    3. Sum: trait_points + aspect_bonus + extra_modifiers = total_points
    4. total_points -> CheckRank -> ResultChart (existing pipeline)
    5. Roll 1-100
    6. Apply rollmod: effective = max(1, min(100, roll + rollmod))
    7. Look up outcome on chart using effective roll
    8. Return CheckResult with possible outcomes list
    """
    handler: TraitHandler = cast(Any, character).traits
    level = _get_character_level(character)

    trait_points = _calculate_trait_points(handler, check_type)
    aspect_bonus = _calculate_aspect_bonus(character, check_type, level)
    total_points = trait_points + aspect_bonus + extra_modifiers

    roller_rank = CheckRank.get_rank_for_points(total_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)

    roller_rank_value = roller_rank.rank if roller_rank else 0
    target_rank_value = target_rank.rank if target_rank else 0
    rank_difference = roller_rank_value - target_rank_value

    chart = ResultChart.get_chart_for_difference(rank_difference)

    roll = random.randint(1, 100)  # noqa: S311
    rollmod = _get_rollmod(character)
    effective_roll = max(1, min(100, roll + rollmod))

    outcome = _get_outcome_for_roll(chart, effective_roll) if chart else None
    possible_outcomes = _get_possible_outcomes(chart) if chart else []

    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=chart,
        roller_rank=roller_rank,
        target_rank=target_rank,
        rank_difference=rank_difference,
        trait_points=trait_points,
        aspect_bonus=aspect_bonus,
        total_points=total_points,
        possible_outcomes=possible_outcomes,
    )


def _calculate_aspect_bonus(
    character: "ObjectDB",
    check_type: "CheckType",
    level: int,
) -> int:
    """
    Calculate aspect bonus from the character's most recent path.

    1. Get character's most recent path from CharacterPathHistory (ordered by -selected_at)
    2. Get PathAspect weights for that path
    3. For each CheckTypeAspect, find matching PathAspect weight
    4. bonus += int(check_aspect_weight * path_aspect_weight * level)
    5. Return total
    """
    latest_history = (
        CharacterPathHistory.objects.filter(character=character)
        .select_related("path")
        .order_by("-selected_at")
        .first()
    )
    if not latest_history:
        return 0

    path = latest_history.path

    path_aspects = {
        pa.aspect_id: pa.weight
        for pa in PathAspect.objects.filter(character_path=path).select_related("aspect")
    }
    if not path_aspects:
        return 0

    check_type_aspects = cast(Any, check_type).aspects.select_related("aspect").all()

    bonus = 0
    for check_aspect in check_type_aspects:
        path_weight = path_aspects.get(check_aspect.aspect_id, 0)
        if path_weight:
            bonus += int(check_aspect.weight * path_weight * level)

    return bonus


def _calculate_trait_points(handler: "TraitHandler", check_type: "CheckType") -> int:
    """
    Calculate weighted trait points for a check type.

    For each CheckTypeTrait, multiply raw trait value by weight (truncated to int),
    then convert the weighted value to points via PointConversionRange, and sum.
    """
    check_type_traits = cast(Any, check_type).traits.select_related("trait").all()
    total = 0

    for ct_trait in check_type_traits:
        trait = cast(Trait, ct_trait.trait)
        trait_value = handler.get_trait_value(cast(str, trait.name))
        if trait_value > 0:
            weighted_value = int(trait_value * ct_trait.weight)
            if weighted_value > 0:
                total += PointConversionRange.calculate_points(trait.trait_type, weighted_value)

    return total


def _get_character_level(character: "ObjectDB") -> int:
    """
    Get the character's primary class level, or highest level, or default to 1.
    """
    primary = CharacterClassLevel.objects.filter(character=character, is_primary=True).first()
    if primary:
        return cast(int, primary.level)

    highest = CharacterClassLevel.objects.filter(character=character).order_by("-level").first()
    if highest:
        return cast(int, highest.level)

    return 1


def _get_rollmod(character: "ObjectDB") -> int:
    """
    Sum character.sheet_data.rollmod + character.account.player_data.rollmod.

    Uses try/except for missing relations, defaults to 0.
    """
    total = 0

    try:
        sheet_data = cast(Any, character).sheet_data
        total += sheet_data.rollmod
    except (ObjectDoesNotExist, AttributeError):
        pass

    try:
        account = cast(Any, character).account
        if account:
            player_data = account.player_data
            total += player_data.rollmod
    except (ObjectDoesNotExist, AttributeError):
        pass

    return total


def _get_outcome_for_roll(chart: "ResultChart", roll: int) -> CheckOutcome | None:
    """Query ResultChartOutcome for matching roll range, return the CheckOutcome."""
    chart_outcome = (
        ResultChartOutcome.objects.filter(
            chart=chart,
            min_roll__lte=roll,
            max_roll__gte=roll,
        )
        .select_related("outcome")
        .first()
    )
    if chart_outcome:
        return chart_outcome.outcome
    return None


def _get_possible_outcomes(chart: "ResultChart") -> list[OutcomeSummary]:
    """Return list of OutcomeSummary for each outcome range on the chart."""
    outcomes = (
        ResultChartOutcome.objects.filter(chart=chart)
        .select_related("outcome")
        .order_by("min_roll")
    )
    return [
        OutcomeSummary(
            name=rco.outcome.name,
            description=rco.outcome.description,
            success_level=rco.outcome.success_level,
            min_roll=rco.min_roll,
            max_roll=rco.max_roll,
        )
        for rco in outcomes
    ]
