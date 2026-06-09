"""Check resolution service functions."""

import random
from typing import TYPE_CHECKING, cast

from django.core.exceptions import ObjectDoesNotExist

from world.checks.constants import ModifierSourceKind
from world.checks.types import CheckResult, ModifierBreakdown, ModifierContribution
from world.classes.models import CharacterClassLevel, PathAspect
from world.fatigue.constants import EFFORT_CHECK_MODIFIER
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

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.traits.handlers import TraitHandler


def perform_check(  # noqa: PLR0913 - optional effort/fatigue params extend existing signature
    character: "ObjectDB",
    check_type: "CheckType",
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
    effort_level: str | None = None,
    fatigue_penalty: int = 0,
) -> CheckResult:
    """
    Main check resolution function.

    1. Calculate weighted trait points using TraitHandler
    2. Calculate aspect bonus from path
    3. Sum: trait_points + aspect_bonus + extra_modifiers + effort_modifier + fatigue_penalty
    4. total_points -> CheckRank -> ResultChart (existing pipeline)
    5. Roll 1-100
    6. Apply rollmod: effective = max(1, min(100, roll + rollmod))
    7. Look up outcome on chart using effective roll
    8. Return CheckResult

    Args:
        character: The character performing the check.
        check_type: The type of check being performed.
        target_difficulty: Target difficulty in points.
        extra_modifiers: Additional modifiers from caller (goals, magic, etc.).
        effort_level: Optional EffortLevel value. Applies effort check modifier.
        fatigue_penalty: Penalty from fatigue zone (caller-computed, typically negative).
    """
    # Test-rig seam (NOT a production code path).
    from world.checks.test_helpers import _consume_forced_outcome, _record_capture  # noqa: PLC0415

    _record_capture(check_type=check_type, target_difficulty=target_difficulty)

    forced_outcome = _consume_forced_outcome()
    if forced_outcome is not None:
        return _build_forced_check_result(
            character=character,
            check_type=check_type,
            forced_outcome=forced_outcome,
            target_difficulty=target_difficulty,
            extra_modifiers=extra_modifiers,
            effort_level=effort_level,
            fatigue_penalty=fatigue_penalty,
        )

    handler: TraitHandler = character.traits  # type: ignore[attr-defined] — ObjectDB typeclass extension
    level = _get_character_level(character)

    effort_modifier = EFFORT_CHECK_MODIFIER.get(effort_level, 0) if effort_level else 0

    trait_points = _calculate_trait_points(handler, check_type)
    aspect_bonus = _calculate_aspect_bonus(character, check_type, level)
    total_points = trait_points + aspect_bonus + extra_modifiers + effort_modifier + fatigue_penalty

    roller_rank = CheckRank.get_rank_for_points(total_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)

    roller_rank_value = roller_rank.rank if roller_rank else 0
    target_rank_value = target_rank.rank if target_rank else 0
    rank_difference = roller_rank_value - target_rank_value

    chart = ResultChart.get_chart_for_difference(rank_difference)

    roll = random.randint(1, 100)  # noqa: S311
    rollmod = get_rollmod(character)
    effective_roll = max(1, min(100, roll + rollmod))

    outcome = _get_outcome_for_roll(chart, effective_roll) if chart else None

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
    )


def _build_forced_check_result(  # noqa: PLR0913 - mirrors perform_check signature for test seam
    character: "ObjectDB",
    check_type: "CheckType",
    forced_outcome: CheckOutcome,
    target_difficulty: int,
    extra_modifiers: int,
    effort_level: str | None,
    fatigue_penalty: int,
) -> CheckResult:
    """Build a synthetic CheckResult for the test-rig forced-outcome path.

    Computes real rank breakdowns from target_difficulty so callers that
    inspect ranks see something reasonable. Skips the dice roll entirely.
    NOT a production code path — only reached inside force_check_outcome().
    """
    handler: TraitHandler = character.traits  # type: ignore[attr-defined] — ObjectDB typeclass extension
    level = _get_character_level(character)

    effort_modifier = EFFORT_CHECK_MODIFIER.get(effort_level, 0) if effort_level else 0

    trait_points = _calculate_trait_points(handler, check_type)
    aspect_bonus = _calculate_aspect_bonus(character, check_type, level)
    total_points = trait_points + aspect_bonus + extra_modifiers + effort_modifier + fatigue_penalty

    roller_rank = CheckRank.get_rank_for_points(total_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)

    roller_rank_value = roller_rank.rank if roller_rank else 0
    target_rank_value = target_rank.rank if target_rank else 0
    rank_difference = roller_rank_value - target_rank_value

    chart = ResultChart.get_chart_for_difference(rank_difference)

    return CheckResult(
        check_type=check_type,
        outcome=forced_outcome,
        chart=chart,
        roller_rank=roller_rank,
        target_rank=target_rank,
        rank_difference=rank_difference,
        trait_points=trait_points,
        aspect_bonus=aspect_bonus,
        total_points=total_points,
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

    check_type_aspects = check_type.aspects.select_related("aspect").all()  # type: ignore[attr-defined] — reverse FK manager from CheckTypeAspect

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
    check_type_traits = check_type.traits.select_related("trait").all()  # type: ignore[attr-defined] — reverse FK manager from CheckTypeTrait
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


def get_rollmod(character: "ObjectDB") -> int:
    """
    Sum character.sheet_data.rollmod + character.account.player_data.rollmod.

    Uses try/except for missing relations, defaults to 0.
    """
    total = 0

    try:
        sheet_data = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
        total += sheet_data.rollmod
    except (ObjectDoesNotExist, AttributeError):
        pass

    try:
        account = character.account  # type: ignore[attr-defined] — ObjectDB typeclass extension
        if account:
            player_data = account.player_data
            total += player_data.rollmod
    except (ObjectDoesNotExist, AttributeError):
        pass

    return total


def preview_check_difficulty(
    character: "ObjectDB",
    check_type: "CheckType",
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
) -> int:
    """
    Preview the rank difference for a check without rolling.

    Returns the rank difference (positive = character is stronger, negative = weaker).
    Uses the same calculation as perform_check steps 1-4.
    """
    handler: TraitHandler = character.traits  # type: ignore[attr-defined] — ObjectDB typeclass extension
    level = _get_character_level(character)

    trait_points = _calculate_trait_points(handler, check_type)
    aspect_bonus = _calculate_aspect_bonus(character, check_type, level)
    total_points = trait_points + aspect_bonus + extra_modifiers

    roller_rank = CheckRank.get_rank_for_points(total_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)

    roller_rank_value = roller_rank.rank if roller_rank else 0
    target_rank_value = target_rank.rank if target_rank else 0
    return roller_rank_value - target_rank_value


def chart_has_success_outcomes(rank_difference: int) -> bool:
    """Check if the ResultChart for this rank difference has any success outcomes."""
    chart = ResultChart.get_chart_for_difference(rank_difference)
    if chart is None:
        return False
    return ResultChartOutcome.objects.filter(
        chart=chart,
        outcome__success_level__gt=0,
    ).exists()


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


def collect_check_modifiers(
    character_sheet: "CharacterSheet",
    check_type: "CheckType",
    *,
    scene: object = None,  # noqa: ARG001 — reserved for P3 scene-modifier wiring
    extra_contributions: list[ModifierContribution] | None = None,
) -> ModifierBreakdown:
    """Aggregate all modifier contributions for a check into a ModifierBreakdown.

    This is the central seam that Phase 1 funnels through.  P3 (Tasks 3.1/3.2)
    will add SCENE and EQUIPMENT contributions once those models exist; the
    ``scene`` parameter is accepted now for forward-compatibility but is unused
    until then — do not add queries against scene/equipment here yet.

    Args:
        character_sheet: The CharacterSheet of the character making the check.
            The ObjectDB character is derived via ``character_sheet.character``
            for callers (like get_rollmod) that still operate on ObjectDB.
        check_type: The CheckType being resolved.
        scene: Reserved for Phase 3 scene-modifier wiring (Tasks 3.1/3.2).
            Pass None; any non-None value is silently ignored until P3 lands.
        extra_contributions: Caller-supplied, already-labeled contributions
            (e.g. combat strain/affinity tilt, effort) to fold into the same
            breakdown so every check honors every modifier source through one
            seam.  Appended AFTER the gathered condition/rollmod contributions
            to keep ordering stable.  Pass None when there are none.

    Returns:
        ModifierBreakdown whose .total is the sum of all contributions and
        whose .contributions list carries full source provenance.
    """
    # Lazy import avoids a circular dependency: world.conditions.services
    # already imports from world.checks, so a module-level import here would
    # create a cycle.  The noqa: PLC0415 token opts this import out of the
    # "no lazy imports" lint rule (same pattern used throughout the repo).
    from world.conditions.services import condition_contributions  # noqa: PLC0415

    contributions: list[ModifierContribution] = []

    # --- CONDITION contributions ---
    contributions.extend(condition_contributions(character_sheet, check_type))

    # --- ROLLMOD contribution ---
    # get_rollmod sums sheet_data.rollmod + account.player_data.rollmod;
    # it operates on the ObjectDB character, so walk back from the sheet.
    rollmod_value = get_rollmod(character_sheet.character)
    if rollmod_value != 0:
        contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.ROLLMOD,
                source_label="Roll modifier",
                value=rollmod_value,
            )
        )

    # SCENE / EQUIPMENT sources are wired in P3 (Tasks 3.1/3.2); not yet.

    # --- CALLER-SUPPLIED contributions (combat strain/affinity, effort, ...) ---
    # Appended last so the gathered condition/rollmod ordering stays stable.
    if extra_contributions:
        contributions.extend(extra_contributions)

    return ModifierBreakdown(contributions=contributions)
