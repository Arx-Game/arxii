"""The sacrifice check and its weekly limit (#4500, #4462 section 6.2).

Giving an item up is a check, not a payment. The item's meaning points ease the
invocation check's difficulty, the roll's outcome tier selects a ``FavorOutcomeAward``
row of kind SACRIFICE, and that is the base favor ``bump_devotion`` then scales by the
earning rate. Nothing here reads an item's price, a fee or a material cost: the points
come from ``world.items.services.meaning.item_meaning``.

The difficulty starts where an invocation's does (``invocation_difficulty``: the base,
the Chosen ease, the favor ease and the favor invocation modifiers, so those keep
applying) and is then eased by ``points x DevotionConfig.sacrifice_ease_per_point``,
never below Trivial.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.checks.constants import BOTCH_SUCCESS_LEVEL_MAX
from world.scenes.action_constants import DIFFICULTY_VALUES, MIN_DIFFICULTY_POINTS
from world.worship.constants import FavorAwardKind
from world.worship.invocation_services import (
    get_devotion_config,
    invocation_check_type,
    invocation_difficulty,
)
from world.worship.types import SacrificeOdds, SacrificeOddsBand, SacrificeOddsLine

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.game_clock.models import GameWeek
    from world.traits.models import CheckOutcome
    from world.worship.models import WorshippedBeing


def is_botch(outcome: CheckOutcome | None) -> bool:
    """True for a Critical Failure: an outcome at or below the botch boundary."""
    return outcome is not None and outcome.success_level <= BOTCH_SUCCESS_LEVEL_MAX


def _week_offerings(sheet: CharacterSheet, being: WorshippedBeing, game_week: GameWeek):
    from world.ceremonies.models import CeremonyOffering  # noqa: PLC0415

    return CeremonyOffering.objects.filter(
        Q(being=being) | Q(ceremony__being=being),
        offered_by__character_sheet=sheet,
        game_week=game_week,
    )


def sacrifice_slots_left(
    sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> int:
    """How many more items with meaning points ``being`` takes from ``sheet`` this game week.

    The limit is ``DevotionConfig.sacrifices_per_week`` per being, per character, at
    shrines and in ceremonies together. A Critical Failure on a sacrifice this week closes
    the being's hand to that character until the next one: 0.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    week = game_week if game_week is not None else get_current_game_week()
    offerings = _week_offerings(sheet, being, week)
    if offerings.filter(outcome_tier__success_level__lte=BOTCH_SUCCESS_LEVEL_MAX).exists():
        return 0
    used = offerings.filter(counted=True).count()
    return max(get_devotion_config().sacrifices_per_week - used, 0)


def sacrifice_difficulty(sheet: CharacterSheet, being: WorshippedBeing, points: int) -> int:
    """The sacrifice check's difficulty in points for an item worth ``points``."""
    eased = invocation_difficulty(sheet, being).points
    eased -= points * get_devotion_config().sacrifice_ease_per_point
    return max(eased, MIN_DIFFICULTY_POINTS)


def sacrifice_configured(being: WorshippedBeing) -> bool:
    """Whether a sacrifice check can roll: the being or the devotion config names a type."""
    return invocation_check_type(being) is not None


def roll_sacrifice(sheet: CharacterSheet, being: WorshippedBeing, difficulty: int) -> CheckResult:
    """Roll ``sheet``'s invocation check type for a sacrifice at ``difficulty`` points.

    The check type is the being's own, else the devotion config's, with the being's
    tradition specialization, as for an invocation. ``difficulty`` comes from
    ``sacrifice_difficulty`` (the caller stores it on the offering). Raises nothing for a
    missing type: callers check ``sacrifice_configured`` first.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    return perform_check_with_modifiers(
        sheet.character,
        invocation_check_type(being),
        target_difficulty=difficulty,
        specialization=being.tradition.rites_specialization,
        extra_traits=activity_skill_terms(MagicActivity.INVOCATION),
    )


def sacrifice_odds(
    difficulty_points: int, *, roller_points: int | None = None
) -> SacrificeOdds | None:
    """The odds of a check at ``difficulty_points`` for a reference roller (#4500).

    Read from the same tables the check pipeline rolls against: the rank gap between the
    roller's points and the difficulty (``CheckRank.get_rank_difference``) picks the
    ``ResultChart`` (``get_chart_for_difference``), and each ``ResultChartOutcome`` band
    (1 to 100) is that outcome's chance in percent. Nothing is hardcoded. The reference
    roller is ``DevotionConfig.odds_reference_roller_points``. None when no chart exists.
    """
    from world.traits.models import CheckRank, ResultChart  # noqa: PLC0415

    roller = (
        roller_points
        if roller_points is not None
        else (get_devotion_config().odds_reference_roller_points)
    )
    chart = ResultChart.get_chart_for_difference(
        CheckRank.get_rank_difference(roller, difficulty_points)
    )
    if chart is None:
        return None
    rank = CheckRank.get_rank_for_points(roller)
    lines = [
        SacrificeOddsLine(
            outcome_name=row.outcome.name,
            success_level=row.outcome.success_level,
            percent=row.max_roll - row.min_roll + 1,
        )
        for row in chart.outcomes.select_related("outcome").order_by("min_roll")
    ]
    return SacrificeOdds(
        difficulty_points=difficulty_points,
        reference_rank_name=rank.name if rank is not None else "",
        lines=lines,
    )


def sacrifice_odds_bands() -> list[SacrificeOddsBand]:
    """The odds for a stranger's sacrifice by meaning points, merged into runs that roll
    on the same chart: "1 to 2 points", "3 to 5", "6 or more" at the example settings.

    Starts from ``DevotionConfig.base_difficulty`` and eases it by
    ``sacrifice_ease_per_point`` a point until the Trivial floor. The bands are derived
    from the charts and the config, never listed here. Empty without charts or ease.
    """
    config = get_devotion_config()
    ease = config.sacrifice_ease_per_point
    base = DIFFICULTY_VALUES[config.base_difficulty]
    if ease <= 0:
        return []
    bands: list[SacrificeOddsBand] = []
    points = 1
    while True:
        difficulty = max(base - points * ease, MIN_DIFFICULTY_POINTS)
        odds = sacrifice_odds(difficulty)
        if odds is None:
            return []
        at_floor = difficulty == MIN_DIFFICULTY_POINTS
        previous = bands[-1] if bands else None
        if previous is not None and previous.odds.lines == odds.lines:
            bands[-1] = SacrificeOddsBand(previous.first_points, points, odds)
        else:
            bands.append(SacrificeOddsBand(points, points, odds))
        if at_floor:
            last = bands[-1]
            bands[-1] = SacrificeOddsBand(last.first_points, None, last.odds)
            return bands
        points += 1


def sacrifice_award(outcome: CheckOutcome | None) -> int:
    """The SACRIFICE base favor for ``outcome``; no row (or no outcome) pays nothing."""
    from world.worship.models import FavorOutcomeAward  # noqa: PLC0415

    if outcome is None:
        return 0
    award = FavorOutcomeAward.objects.filter(
        config=get_devotion_config(), kind=FavorAwardKind.SACRIFICE, outcome_tier=outcome
    ).first()
    return award.amount if award is not None else 0
