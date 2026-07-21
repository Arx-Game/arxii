"""Check resolution service functions."""

from decimal import Decimal
import random
from typing import TYPE_CHECKING, NamedTuple, cast

from django.core.exceptions import ObjectDoesNotExist

from world.checks.constants import BOTCH_SUCCESS_LEVEL_MAX, ModifierSourceKind
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
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
    TraitType,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType, CheckTypeCapabilityModifier, Consequence
    from world.covenants.models import VowSituationalPerk
    from world.covenants.perks.context import SituationContext
    from world.mechanics.models import CharacterChallengeRecord
    from world.scenes.models import Interaction, Scene
    from world.skills.models import Specialization
    from world.traits.handlers import TraitHandler


def perform_check(  # noqa: PLR0913 - optional effort/fatigue params extend existing signature
    character: "ObjectDB",
    check_type: "CheckType",
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
    effort_level: str | None = None,
    fatigue_penalty: int = 0,
    specialization: "Specialization | None" = None,
    *,
    situation_ctx: "SituationContext | None" = None,
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
        situation_ctx: (#2536, Task 5; ``.attacker`` added slice 3 Task 6) the
            checking character's own ``SituationContext`` — only
            ``.resolution`` (a ``CombatRoundContext`` or ``None``),
            ``.target``, and ``.attacker`` (the defense-side attacking
            entity, or ``None`` on offense) are read; ``.holder``/``.subject``
            are unused here (the checking character's ``CharacterSheet`` is
            resolved from ``character`` directly). ``None`` (the default) is
            byte-identical to pre-#2536 behavior — no query, no perk lookup.
            When provided, fires ``CHECK_BONUS`` situational perks
            (``world.covenants.perks``) scoped to ``check_type`` (or
            scope-less perks) and folds their thread-level-scaled magnitude
            into the same total ``extra_modifiers`` feeds — see
            ``_situational_perk_check_bonus``. It also fires
            ``TIER_FLOOR``/``BOTCH_IMMUNITY`` outcome guarantees (#2536 slice 2)
            AFTER the outcome lands (both the rolled and the test-rig forced
            path), raising the outcome to the effective floor when it landed
            below one and announcing only when a guarantee actually altered
            the outcome — see ``_apply_outcome_guarantees``.
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
            specialization=specialization,
            situation_ctx=situation_ctx,
        )

    breakdown = _compute_check_breakdown(
        character,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=extra_modifiers,
        effort_level=effort_level,
        fatigue_penalty=fatigue_penalty,
        specialization=specialization,
        situation_ctx=situation_ctx,
    )

    roll = random.randint(1, 100)  # noqa: S311
    rollmod = get_rollmod(character)
    effective_roll = max(1, min(100, roll + rollmod))
    outcome = _get_outcome_for_roll(breakdown.chart, effective_roll) if breakdown.chart else None
    outcome = _apply_outcome_guarantees(character, outcome, breakdown.chart, situation_ctx)

    return _check_result(check_type, outcome, breakdown)


def _build_forced_check_result(  # noqa: PLR0913 - mirrors perform_check signature for test seam
    character: "ObjectDB",
    check_type: "CheckType",
    forced_outcome: CheckOutcome,
    target_difficulty: int,
    extra_modifiers: int,
    effort_level: str | None,
    fatigue_penalty: int,
    specialization: "Specialization | None" = None,
    situation_ctx: "SituationContext | None" = None,
) -> CheckResult:
    """Build a synthetic CheckResult for the test-rig forced-outcome path.

    Computes real rank breakdowns from target_difficulty so callers that
    inspect ranks see something reasonable. Skips the dice roll entirely.
    NOT a production code path — only reached inside force_check_outcome().

    Outcome guarantees (#2536 slice 2, ``_apply_outcome_guarantees``) apply to
    forced outcomes too — the deterministic way tests exercise TIER_FLOOR /
    BOTCH_IMMUNITY (e.g. a forced botch through a botch-immune character's
    check comes out a plain failure), not just the real dice-roll path.
    """
    breakdown = _compute_check_breakdown(
        character,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=extra_modifiers,
        effort_level=effort_level,
        fatigue_penalty=fatigue_penalty,
        specialization=specialization,
        situation_ctx=situation_ctx,
    )
    outcome = _apply_outcome_guarantees(character, forced_outcome, breakdown.chart, situation_ctx)
    return _check_result(check_type, outcome, breakdown)


class _CheckBreakdown(NamedTuple):
    """The point/rank/chart breakdown shared by the rolled and forced check paths (#1688)."""

    trait_points: int
    specialization_points: int
    aspect_bonus: int
    capability_points: int
    total_points: int
    roller_rank: "CheckRank | None"
    target_rank: "CheckRank | None"
    rank_difference: int
    chart: "ResultChart | None"


def _compute_check_breakdown(  # noqa: PLR0913 - keyword-only check params mirror perform_check
    character: "ObjectDB",
    check_type: "CheckType",
    *,
    target_difficulty: int,
    extra_modifiers: int,
    effort_level: str | None,
    fatigue_penalty: int,
    specialization: "Specialization | None",
    situation_ctx: "SituationContext | None" = None,
) -> _CheckBreakdown:
    """Compute stat + skill + specialization + aspect points, ranks, and chart (no dice roll).

    Shared by ``perform_check`` (which then rolls) and the forced-outcome test path (which
    supplies the outcome directly) — the single source of the check's point math.
    """
    handler: TraitHandler = character.traits  # type: ignore[attr-defined] — ObjectDB typeclass extension
    level = _get_character_level(character)
    effort_modifier = EFFORT_CHECK_MODIFIER.get(effort_level, 0) if effort_level else 0

    trait_points = _calculate_trait_points(handler, check_type)
    specialization_points = _calculate_specialization_points(character, check_type, specialization)
    aspect_bonus = _calculate_aspect_bonus(character, check_type, level)
    capability_points = _calculate_capability_points(character, check_type)
    perk_bonus = _situational_perk_check_bonus(character, check_type, situation_ctx)
    total_points = (
        trait_points
        + specialization_points
        + aspect_bonus
        + capability_points
        + extra_modifiers
        + perk_bonus
        + effort_modifier
        + fatigue_penalty
    )

    roller_rank = CheckRank.get_rank_for_points(total_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)
    rank_difference = (roller_rank.rank if roller_rank else 0) - (
        target_rank.rank if target_rank else 0
    )
    chart = ResultChart.get_chart_for_difference(rank_difference)

    return _CheckBreakdown(
        trait_points=trait_points,
        specialization_points=specialization_points,
        aspect_bonus=aspect_bonus,
        capability_points=capability_points,
        total_points=total_points,
        roller_rank=roller_rank,
        target_rank=target_rank,
        rank_difference=rank_difference,
        chart=chart,
    )


def _situational_perk_check_bonus(
    character: "ObjectDB",
    check_type: "CheckType",
    situation_ctx: "SituationContext | None",
) -> int:
    """Σ fired ``CHECK_BONUS`` situational perks scaled by thread level (#2536, Task 5).

    Mirrors ``vow_situational_power_term``'s arithmetic exactly (same
    thread-level scaling, same integer truncation after summing in
    ``Decimal``) but scopes fired perks to ``check_type``: a perk with
    ``check_type=None`` fires on any check; a perk scoped to a specific
    ``CheckType`` fires only when it matches THIS check. Also applies
    ``perks.services.perk_scope_matches`` (#2536 slice 3) — the shared
    mission/battle scope filter both this function and
    ``vow_situational_power_term`` run every fired perk through.

    Returns 0 with no query beyond resolving the character's
    ``CharacterSheet`` when ``situation_ctx`` is ``None`` — the
    byte-identical default every pre-#2536 ``perform_check`` caller takes.
    A character with no ``CharacterSheet`` (``sheet_data``) also contributes
    0 and never raises — mirrors the guard in ``_calculate_capability_points``.

    Announces (#2536 Task 6) every check-type-scoped firing exactly once
    here — this function is called exactly once per ``perform_check``
    breakdown computation (the normal-roll and test-rig forced-outcome
    branches are mutually exclusive, never both), so this is the ONE place
    a CHECK_BONUS firing can be announced without risking a double-announce.
    See ``perks.services.announce_fired_perks``'s docstring.

    Makes ONE dormant pass right after computing the live firings (#2536
    slice 3, Task 7 — ruling 2's "loud OFF state"): a DISENGAGED role that
    would have answered this check announces the dormant line to the
    subject alone, respecting the SAME ``check_type`` + scope filters the
    live set goes through — see ``perks.services.dormant_perk_firings``/
    ``announce_dormant_perks``. Fires even when ``fired`` (the live,
    engaged set) is empty — a wholly-disengaged vow has no live firings at
    all, but that is exactly the case ruling 2 wants to be loud about.
    """
    if situation_ctx is None:
        return 0

    try:
        sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    except (ObjectDoesNotExist, AttributeError):
        return 0

    from world.covenants.perks.constants import PerkEffectKind  # noqa: PLC0415
    from world.covenants.perks.services import (  # noqa: PLC0415
        announce_dormant_perks,
        announce_fired_perks,
        applicable_perks,
        dormant_perk_firings,
        mission_category_ids_for,
        perk_scope_matches,
    )
    from world.magic.services.threads import (  # noqa: PLC0415
        total_thread_level_across_all_kinds,
    )

    fired = applicable_perks(
        sheet,
        effect_kind=PerkEffectKind.CHECK_BONUS,
        resolution=situation_ctx.resolution,
        target=situation_ctx.target,
        attacker=situation_ctx.attacker,
    )

    dormant = dormant_perk_firings(
        sheet,
        effect_kind=PerkEffectKind.CHECK_BONUS,
        resolution=situation_ctx.resolution,
        target=situation_ctx.target,
        mission=situation_ctx.mission,
        battle_action_kind=situation_ctx.battle_action_kind,
        attacker=situation_ctx.attacker,
    )
    if dormant:
        dormant_scoped = [
            firing
            for firing in dormant
            if firing.perk.check_type_id is None or firing.perk.check_type_id == check_type.pk
        ]
        announce_dormant_perks(dormant_scoped, subject=sheet)

    scoped = [
        firing
        for firing in fired
        if firing.perk.check_type_id is None or firing.perk.check_type_id == check_type.pk
    ]
    # #2536 slice 3 review fix: hoist the mission-category set ONCE for this
    # resolution rather than re-querying it per scoped perk below.
    mission_category_ids = mission_category_ids_for(situation_ctx)
    scoped = [
        f
        for f in scoped
        if perk_scope_matches(f.perk, situation_ctx, mission_category_ids=mission_category_ids)
    ]
    if not scoped:
        return 0

    announce_fired_perks(scoped, subject=sheet, location=character.location)

    total_threads = total_thread_level_across_all_kinds(sheet)
    if total_threads == 0:
        return 0

    total = Decimal(0)
    for firing in scoped:
        total += Decimal(total_threads) * firing.magnitude_tenths / 10
    return int(total)


def _guarantee_floor(
    perk: "VowSituationalPerk", *, raw_level: int, non_botch_floor: int
) -> int | None:
    """The floor a TIER_FLOOR/BOTCH_IMMUNITY perk demands against ``raw_level``,
    or ``None`` when it never applies here (#2536 slice 2/3). Shared by the
    live-binding computation and the dormant "would it have bound" check in
    ``_apply_outcome_guarantees`` — one rule, one place.
    """
    from world.covenants.perks.constants import PerkEffectKind  # noqa: PLC0415

    if perk.effect_kind == PerkEffectKind.TIER_FLOOR:
        return perk.floor_success_level
    # BOTCH_IMMUNITY -- binds only against an actual botch.
    return non_botch_floor if raw_level <= BOTCH_SUCCESS_LEVEL_MAX else None


def _announce_dormant_outcome_guarantees(
    sheet: "CharacterSheet",
    situation_ctx: "SituationContext",
    kinds: tuple[str, ...],
    raw_level: int,
) -> None:
    """The dormant half of ``_apply_outcome_guarantees`` (#2536 slice 3, Task 7 —
    ruling 2's "loud OFF state"), split out to keep the main function's
    branching within the complexity budget. Announces a DISENGAGED guarantee
    perk only when it WOULD have bound against the RAW outcome — never merely
    because a disengaged perk exists.
    """
    from world.covenants.perks.services import (  # noqa: PLC0415
        announce_dormant_perks,
        dormant_perk_firings,
    )

    dormant = dormant_perk_firings(
        sheet,
        effect_kind=kinds,
        resolution=situation_ctx.resolution,
        target=situation_ctx.target,
        mission=situation_ctx.mission,
        battle_action_kind=situation_ctx.battle_action_kind,
        attacker=situation_ctx.attacker,
    )
    if not dormant:
        return

    non_botch_floor = BOTCH_SUCCESS_LEVEL_MAX + 1
    would_have_bound = []
    for firing in dormant:
        floor = _guarantee_floor(firing.perk, raw_level=raw_level, non_botch_floor=non_botch_floor)
        if floor is not None and floor > raw_level:
            would_have_bound.append(firing)
    if would_have_bound:
        announce_dormant_perks(would_have_bound, subject=sheet)


def _apply_outcome_guarantees(
    character: "ObjectDB",
    outcome: "CheckOutcome | None",
    chart: "ResultChart | None",
    situation_ctx: "SituationContext | None",
) -> "CheckOutcome | None":
    """Raise ``outcome`` to the effective TIER_FLOOR / BOTCH_IMMUNITY floor (#2536 slice 2).

    Apostate's principle: you can't botch at the thing your character is
    specifically here to do — outcome GUARANTEES, not numeric bonuses. Both
    kinds fire through ``applicable_perks`` in ONE call (tuple effect_kind) and
    are ABSOLUTE: no thread-level scaling, no thread-level gate (ungated ruling,
    2026-07-20). A TIER_FLOOR firing guarantees ``success_level >=
    perk.floor_success_level``; a BOTCH_IMMUNITY firing only binds when the raw
    outcome is a botch (``success_level <= BOTCH_SUCCESS_LEVEL_MAX``) and floors
    it at the least-bad non-botch level. The replacement outcome is the chart's
    lowest outcome at/above the effective floor, falling back to the global
    ``CheckOutcome`` table when the chart has none (degenerate charts, forced
    outcomes without chart rows). Announces ONLY the binding perks, ONLY when
    the outcome actually changed — a guarantee that didn't bind is silence, not
    spam. ``situation_ctx=None`` (every pre-slice-2 caller) or ``outcome=None``
    returns unchanged with zero queries.

    Makes ONE dormant pass right after computing the live firings (#2536
    slice 3, Task 7 — ruling 2's "loud OFF state"): a DISENGAGED guarantee
    perk announces only when it WOULD have bound — its floor (or, for
    BOTCH_IMMUNITY, the non-botch floor against an actual raw botch) exceeds
    the RAW outcome's ``success_level`` — never merely because a disengaged
    perk exists. Runs whether or not the live set has any binding perk: a
    wholly-disengaged vow has no live firings at all, which is exactly the
    case ruling 2 wants to be loud about.
    """
    if situation_ctx is None or outcome is None:
        return outcome

    try:
        sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    except (ObjectDoesNotExist, AttributeError):
        return outcome

    from world.covenants.perks.constants import PerkEffectKind  # noqa: PLC0415
    from world.covenants.perks.services import (  # noqa: PLC0415
        announce_fired_perks,
        applicable_perks,
    )

    kinds = (PerkEffectKind.TIER_FLOOR, PerkEffectKind.BOTCH_IMMUNITY)
    raw_level = int(outcome.success_level)
    non_botch_floor = BOTCH_SUCCESS_LEVEL_MAX + 1

    fired = applicable_perks(
        sheet,
        effect_kind=kinds,
        resolution=situation_ctx.resolution,
        target=situation_ctx.target,
        attacker=situation_ctx.attacker,
    )

    _announce_dormant_outcome_guarantees(sheet, situation_ctx, kinds, raw_level)

    if not fired:
        return outcome

    binding = []
    for firing in fired:
        floor = _guarantee_floor(firing.perk, raw_level=raw_level, non_botch_floor=non_botch_floor)
        if floor is not None and floor > raw_level:
            binding.append((floor, firing))
    if not binding:
        return outcome

    effective_floor = max(floor for floor, _firing in binding)
    replacement = _lowest_outcome_at_or_above(chart, effective_floor)
    if replacement is None:
        return outcome

    announce_fired_perks(
        [firing for _floor, firing in binding], subject=sheet, location=character.location
    )
    return replacement


def _lowest_outcome_at_or_above(chart: "ResultChart | None", floor: int) -> "CheckOutcome | None":
    """The least-good outcome satisfying a guarantee floor: chart-scoped first
    (guarantees respect what this chart can produce), global ``CheckOutcome``
    fallback when the chart has no row at/above the floor, ``None`` when no such
    outcome is authored anywhere (guarantee is then a no-op — never invent rows).
    """
    if chart is not None:
        row = (
            ResultChartOutcome.objects.filter(chart=chart, outcome__success_level__gte=floor)
            .select_related("outcome")
            .order_by("outcome__success_level")
            .first()
        )
        if row is not None:
            return row.outcome
    return CheckOutcome.objects.filter(success_level__gte=floor).order_by("success_level").first()


def compute_check_rating(
    character: "ObjectDB",
    check_type: "CheckType",
    extra_modifiers: int = 0,
) -> int:
    """Return *character*'s pre-roll rating (total points) for *check_type* — no dice roll.

    Reuses :func:`_compute_check_breakdown`, the single source of the check's point math
    shared by :func:`perform_check` and the forced-outcome test path, so any caller that
    needs to *compare* a character's standing in two ``CheckType``s (e.g. picking the
    better of two reaction approaches) does so deterministically. ADR-0019 keeps the one
    dice roll inside ``perform_check``/``resolve_challenge`` — this helper never rolls.
    """
    breakdown = _compute_check_breakdown(
        character,
        check_type,
        target_difficulty=0,
        extra_modifiers=extra_modifiers,
        effort_level=None,
        fatigue_penalty=0,
        specialization=None,
    )
    return breakdown.total_points


def _check_result(
    check_type: "CheckType", outcome: "CheckOutcome | None", breakdown: _CheckBreakdown
) -> CheckResult:
    """Assemble a CheckResult from a breakdown + the resolved (rolled or forced) outcome."""
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=breakdown.chart,
        roller_rank=breakdown.roller_rank,
        target_rank=breakdown.target_rank,
        rank_difference=breakdown.rank_difference,
        trait_points=breakdown.trait_points,
        aspect_bonus=breakdown.aspect_bonus,
        total_points=breakdown.total_points,
        specialization_points=breakdown.specialization_points,
        capability_points=breakdown.capability_points,
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


def _calculate_specialization_points(
    character: "ObjectDB",
    check_type: "CheckType",
    runtime_specialization: "Specialization | None" = None,
) -> int:
    """Calculate weighted specialization points for a check (#1688).

    The third leg of stat + skill + **specialization**: each ``CheckTypeSpecialization`` on the
    check (plus an optional ``runtime_specialization`` chosen at call time, e.g. which Performance
    art) adds its owner's value. A character who doesn't own the spec contributes 0 (so a
    non-specialist simply rolls stat + skill). Specialization values scale like skills, so they
    convert through the same ``PointConversionRange`` as a SKILL trait.
    """
    from world.skills.services import get_specialization_value  # noqa: PLC0415 — avoid app cycle

    total = 0
    seen: set[int] = set()
    for ct_spec in check_type.specializations.select_related("specialization").all():  # type: ignore[attr-defined] — reverse FK from CheckTypeSpecialization
        spec = ct_spec.specialization
        seen.add(spec.pk)
        value = get_specialization_value(character, spec)
        if value > 0:
            weighted_value = int(value * ct_spec.weight)
            if weighted_value > 0:
                total += PointConversionRange.calculate_points(TraitType.SKILL, weighted_value)

    if runtime_specialization is not None and runtime_specialization.pk not in seen:
        value = get_specialization_value(character, runtime_specialization)
        if value > 0:
            total += PointConversionRange.calculate_points(TraitType.SKILL, value)

    return total


def _capability_point_allocation(
    character_sheet: "CharacterSheet",
    capability_modifiers: list["CheckTypeCapabilityModifier"],
) -> tuple[int, list[int]]:
    """Shared capability arithmetic (#2505) — the ONLY place either caller computes it.

    Both the rolled total (``_calculate_capability_points``) and the recorded
    provenance (``_capability_contributions``) must agree, so they share this one
    helper instead of each re-deriving the math (a prior version truncated
    per-row in the provenance path, which could diverge from the roll path's
    single truncation — see #2505 review fix).

    1. Raw per-row products: ``weight * get_effective_capability_value(...)`` (Decimal).
    2. ``truncated_total = int(sum(raw_products))`` — truncated toward zero ONCE,
       matching ``CheckTypeCapabilityModifier.weight``'s help_text.
    3. The truncated total is allocated back across rows by **largest remainder**:
       floor each row's raw product toward zero, then distribute the leftover
       units (``truncated_total - sum(floors)``) to the rows with the largest
       fractional remainder, breaking ties by capability name for determinism.
       This guarantees per-row allocated ints sum EXACTLY to ``truncated_total``.

    Returns:
        ``(truncated_total, allocated)`` where ``allocated`` is a list of ints in
        the same order as ``capability_modifiers``. Callers filter zero entries
        AFTER allocation (not before — a row can be nonzero pre-allocation and
        land on zero, or vice versa).
    """
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    raw_products: list[Decimal] = [
        row.weight * get_effective_capability_value(character_sheet, row.capability)
        for row in capability_modifiers
    ]
    truncated_total = int(sum(raw_products)) if raw_products else 0

    floors = [int(product) for product in raw_products]
    leftover = truncated_total - sum(floors)

    if leftover != 0:
        step = 1 if leftover > 0 else -1

        def _remainder_key(i: int) -> tuple[Decimal, str]:
            remainder = abs(raw_products[i] - floors[i])
            return (-remainder, capability_modifiers[i].capability.name)

        order = sorted(range(len(capability_modifiers)), key=_remainder_key)
        for i in order[: abs(leftover)]:
            floors[i] += step

    return truncated_total, floors


def _calculate_capability_points(character: "ObjectDB", check_type: "CheckType") -> int:
    """Weighted capability contribution from authored CheckTypeCapabilityModifier rows (#2505).

    Curated gate: only (check_type, capability) pairs an author has explicitly linked can
    ever move points — a character's raw capability value (however large) has zero effect
    on a check_type with no authored row for it. When there are no authored rows this
    returns 0 without ever calling the capability oracle (no pointless queries).

    Per row: weight x get_effective_capability_value(sheet, capability) — the agency
    oracle (innate baseline + CharacterModifier + condition contributions + passive
    grants). Summed across rows, then truncated toward zero ONCE via
    ``_capability_point_allocation`` (matches CheckTypeCapabilityModifier.weight's
    help_text), analogous to how trait/aspect points truncate.

    A character with no CharacterSheet (``sheet_data``) contributes 0 and never raises —
    mirrors the guard in ``get_rollmod``.
    """
    capability_modifiers = list(
        check_type.capability_modifiers.select_related("capability").all()  # type: ignore[attr-defined] — reverse FK manager from CheckTypeCapabilityModifier
    )
    if not capability_modifiers:
        return 0

    try:
        character_sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    except (ObjectDoesNotExist, AttributeError):
        return 0

    total, _allocated = _capability_point_allocation(character_sheet, capability_modifiers)
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


def compute_resist_increment(defender_character: "ObjectDB", resist_effort_level: str) -> int:
    """Compute how much a defender's active resistance raises difficulty.

    Resolves the Composure CheckType by name (category-agnostic) and sums the
    defender's weighted Composure trait points with the effort-level modifier.
    Result is clamped to ≥ 0 — resistance never lowers the attacker's difficulty.

    Args:
        defender_character: The character resisting the social action.
        resist_effort_level: An EffortLevel string value (e.g. ``"high"``).

    Returns:
        Non-negative integer representing the difficulty increment from resistance.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    composure_check_type = CheckType.objects.filter(name="Composure", is_active=True).first()
    if composure_check_type is None:
        return 0

    handler: TraitHandler = defender_character.traits  # type: ignore[attr-defined]
    points = _calculate_trait_points(handler, composure_check_type)
    modifier = EFFORT_CHECK_MODIFIER.get(resist_effort_level, 0)
    return max(0, points + modifier)


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


def record_consequence_outcome(  # noqa: PLR0913 - consequence resolution needs all context fields
    character_sheet: "CharacterSheet",
    check_type: "CheckType",
    pool,  # actions.ConsequencePool | None — no TYPE_CHECKING import to avoid cross-app cycle
    selected_consequence: "Consequence | None",
    breakdown: ModifierBreakdown,
    *,
    combat_interaction: "Interaction | None" = None,
    challenge_record: "CharacterChallengeRecord | None" = None,
    summary: str = "",
) -> ConsequenceOutcome:
    """Persist one consequence-resolution event as a ConsequenceOutcome + modifier rows.

    Exactly one of ``combat_interaction`` / ``challenge_record`` must be provided;
    ValueError is raised before any DB write if the constraint would be violated.

    ``combat_interaction_timestamp`` is derived from ``combat_interaction.timestamp``
    (the same attribute CombatRoundAction.interaction_timestamp is denormalized from)
    and is populated atomically with the FK, as required by the composite FK
    constraint on the range-partitioned scenes_interaction table.

    Modifier rows are bulk-created in a single query (no per-row saves).

    Args:
        character_sheet: The CharacterSheet of the resolving character.
        check_type: The CheckType that was resolved.
        pool: The actions.ConsequencePool the roulette ran against.
        selected_consequence: The Consequence that was selected (may be None if no
            consequence was triggered).
        breakdown: ModifierBreakdown snapshot at resolution time — its total and
            individual contributions are persisted.
        combat_interaction: Interaction created for the combat resolution.
            Mutually exclusive with challenge_record.
        challenge_record: CharacterChallengeRecord this resolved against.
            Mutually exclusive with combat_interaction.
        summary: Optional human-readable summary string.

    Returns:
        The newly created ConsequenceOutcome instance.

    Raises:
        ValueError: If neither or both of combat_interaction/challenge_record are provided.
    """
    both_set = combat_interaction is not None and challenge_record is not None
    neither_set = combat_interaction is None and challenge_record is None
    if both_set or neither_set:
        raise ValueError(
            "record_consequence_outcome requires exactly one of combat_interaction or "
            "challenge_record; got " + ("both" if both_set else "neither") + "."
        )

    outcome = ConsequenceOutcome.objects.create(
        character=character_sheet,
        check_type=check_type,
        pool=pool,
        selected_consequence=selected_consequence,
        modifier_total=breakdown.total,
        summary=summary,
        combat_interaction=combat_interaction,
        combat_interaction_timestamp=(
            combat_interaction.timestamp if combat_interaction is not None else None
        ),
        challenge_record=challenge_record,
    )

    if breakdown.contributions:
        ConsequenceOutcomeModifier.objects.bulk_create(
            [
                ConsequenceOutcomeModifier(
                    outcome=outcome,
                    source_kind=contribution.source_kind,
                    source_label=contribution.source_label,
                    value=contribution.value,
                )
                for contribution in breakdown.contributions
            ]
        )

    return outcome


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
    scene: "Scene | None" = None,
    extra_contributions: list[ModifierContribution] | None = None,
) -> ModifierBreakdown:
    """Aggregate all modifier contributions for a check into a ModifierBreakdown.

    This is the central seam that Phase 1 funnels through.

    Args:
        character_sheet: The CharacterSheet of the character making the check.
            The ObjectDB character is derived via ``character_sheet.character``
            for callers (like get_rollmod) that still operate on ObjectDB.
        check_type: The CheckType being resolved.
        scene: Optional Scene whose surroundings may modify this check.
            When provided, any SceneCheckModifier rows for (scene, check_type)
            are folded in as SCENE contributions.  Pass None when checks are
            performed outside an active scene.
        extra_contributions: Caller-supplied, already-labeled contributions
            (e.g. combat strain/affinity tilt, effort) to fold into the same
            breakdown so every check honors every modifier source through one
            seam.  Appended AFTER the gathered condition/rollmod/scene
            contributions to keep ordering stable.  Pass None when there are none.

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

    # Guard for SCENE, EQUIPMENT, CHARACTER, and EQUIPMENT-WALK blocks: only run DB
    # queries when check_type is a real persisted model instance.  Callers that mock
    # the check pipeline (e.g. combat resolver tests that pass MagicMock() as
    # offense_check_type) must not trigger live queries.  MagicMock has __iter__ and
    # satisfies hasattr(…, "as_sql"), causing Django to treat it as a SQL
    # subexpression and eventually call list(mock) → [] which raises "Field 'id'
    # expected a number but got []".  isinstance(check_type, Model) is False for
    # MagicMock — not a Django Model subclass — so this reliably skips queries for
    # mocks while remaining transparent for every real-code caller.
    from django.db.models import Model as _DjangoModel  # noqa: PLC0415

    # --- SCENE contributions ---
    # Lazy import: world.scenes.models imports from world.scenes.constants,
    # world.societies, etc. — no cycle risk, but we keep the lazy pattern
    # consistent with condition_contributions for uniformity and to avoid
    # loading the scenes app module at import time of checks.services.
    if scene is not None and isinstance(check_type, _DjangoModel):
        from world.scenes.models import SceneCheckModifier  # noqa: PLC0415

        scene_mods = SceneCheckModifier.objects.filter(
            scene=scene,
            check_type=check_type,
        ).select_related("scene")
        contributions.extend(
            ModifierContribution(
                source_kind=ModifierSourceKind.SCENE,
                source_label=f"Scene surroundings: {mod.scene.name}",
                value=mod.modifier_value,
            )
            for mod in scene_mods
        )

    # --- EQUIPMENT contributions ---
    from world.items.models import ItemCheckModifier  # noqa: PLC0415

    character = character_sheet.character
    if isinstance(check_type, _DjangoModel) and character is not None:
        item_mods = (
            ItemCheckModifier.objects.filter(
                template__instances__equipped_slots__character=character,
                check_type=check_type,
            )
            .select_related("template")
            .distinct()
        )
        contributions.extend(
            ModifierContribution(
                source_kind=ModifierSourceKind.EQUIPMENT,
                source_label=f"Equipped: {mod.template.name}",
                value=mod.modifier_value,
            )
            for mod in item_mods
        )

    # --- CHARACTER + EQUIPMENT-WALK + FASHION contributions (#767, #512) ---
    # All keyed off the same scoped ModifierTarget (the check's reverse
    # ``modifier_target`` OneToOne).  Reuses the isinstance guard above: mocked
    # check types must not hit the ORM, and a reverse OneToOne lookup on a
    # MagicMock would raise anyway.
    if isinstance(check_type, _DjangoModel):
        contributions.extend(
            _character_and_equipment_contributions(character_sheet, check_type, scene)
        )

    # --- CAPABILITY contributions (#2505) ---
    # Authored CheckTypeCapabilityModifier rows. Shares the _capability_point_allocation
    # helper with _calculate_capability_points (the roll path) so recorded provenance always
    # sums to exactly what moved total_points, never independently re-derived. Reuses the
    # isinstance guard: a mocked check_type has no real reverse ``capability_modifiers``
    # manager.
    if isinstance(check_type, _DjangoModel):
        contributions.extend(_capability_contributions(character_sheet, check_type))

    # --- CALLER-SUPPLIED contributions (combat strain/affinity, effort, ...) ---
    # Appended last so the gathered condition/rollmod/scene ordering stays stable.
    if extra_contributions:
        contributions.extend(extra_contributions)

    return ModifierBreakdown(contributions=contributions)


def _character_and_equipment_contributions(
    character_sheet: "CharacterSheet",
    check_type: "CheckType",
    scene: "Scene | None",
) -> list[ModifierContribution]:
    """Contributions keyed off the check's scoped ModifierTarget (#767, #512).

    Resolves ``check_type.modifier_target`` ONCE and shares it between three
    sources that all target the same scoped ModifierTarget:

    * CHARACTER — persistent CharacterModifier rows (e.g. a distinction-granted
      "+penetration vs warded foes" buff). The EAGER ``get_modifier_breakdown``
      rows.
    * EQUIPMENT walk (Spec D §5.5) — facet + covenant-role + mantle passive
      bonuses via ``equipment_walk_total``.
    * FASHION — the perception-relative outfit bonus for the scene's societies
      (max across them), added only when a ``scene`` is supplied.

    **No double count:** ``equipment_walk_total`` / ``fashion_outfit_bonus`` are
    called DIRECTLY, never ``get_modifier_total`` (which would re-add the eager
    breakdown total already emitted as CHARACTER contributions).

    The caller guards this with ``isinstance(check_type, Model)``; the reverse
    OneToOne lookup here would raise on a MagicMock.
    """
    # Mechanics' get_modifier_breakdown / ModifierBreakdown are distinct from
    # this module's checks ModifierBreakdown — import aliased.
    from world.mechanics.services import (  # noqa: PLC0415
        equipment_walk_total,
        fashion_outfit_bonus,
        get_modifier_breakdown as get_character_modifier_breakdown,
    )

    try:
        scoped_target = check_type.modifier_target
    except ObjectDoesNotExist:
        scoped_target = None
    if scoped_target is None or not scoped_target.is_active:
        return []

    contributions: list[ModifierContribution] = []

    # CHARACTER — eager CharacterModifier rows.
    character_breakdown = get_character_modifier_breakdown(character_sheet, scoped_target)
    contributions.extend(
        ModifierContribution(
            source_kind=ModifierSourceKind.CHARACTER,
            source_label=detail.source_name,
            value=detail.final_value,
        )
        for detail in character_breakdown.sources
        if not detail.blocked_by_immunity and detail.final_value != 0
    )

    # EQUIPMENT-INSTANCE — per-instance crafted mods (#1567)
    character = character_sheet.character
    if character is not None:
        try:
            crafted_value = character.equipped_items.crafted_modifier_total(scoped_target)
        except AttributeError:
            crafted_value = 0
        if crafted_value != 0:
            contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.EQUIPMENT,
                    source_label="Crafted modifiers",
                    value=crafted_value,
                )
            )

    # EQUIPMENT walk — facet + covenant-role + mantle passive bonuses.
    walk = equipment_walk_total(character_sheet, scoped_target)
    if walk:
        contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.EQUIPMENT,
                source_label="Equipment & attunement",
                value=walk,
            )
        )

    # FASHION — perception-relative outfit bonus (best across scene societies).
    if scene is not None:
        from world.areas.services import societies_for_scene  # noqa: PLC0415

        societies = societies_for_scene(scene)
        fashion = max(
            (
                fashion_outfit_bonus(character_sheet, scoped_target, society)
                for society in societies
            ),
            default=0,
        )
        if fashion:
            contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.FASHION,
                    source_label="Fashion",
                    value=fashion,
                )
            )

    return contributions


def _capability_contributions(
    character_sheet: "CharacterSheet", check_type: "CheckType"
) -> list[ModifierContribution]:
    """CAPABILITY contributions from authored CheckTypeCapabilityModifier rows (#2505).

    Uses ``_capability_point_allocation`` — the same helper ``_calculate_capability_points``
    calls — so the per-row values recorded here (ModifierBreakdown / ConsequenceOutcomeModifier
    provenance) always sum EXACTLY to the same truncated total that moved ``total_points`` on
    the roll path. The truncated total is allocated back across rows by largest remainder
    (see ``_capability_point_allocation`` docstring); zero-value rows are dropped only AFTER
    that allocation. No authored rows -> no queries beyond ``check_type.capability_modifiers``
    itself (the curated gate).
    """
    capability_modifiers = list(
        check_type.capability_modifiers.select_related("capability").all()  # type: ignore[attr-defined] — reverse FK manager from CheckTypeCapabilityModifier
    )
    if not capability_modifiers:
        return []

    _total, allocated = _capability_point_allocation(character_sheet, capability_modifiers)

    contributions: list[ModifierContribution] = []
    for row, value in zip(capability_modifiers, allocated, strict=True):
        if value != 0:
            contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.CAPABILITY,
                    source_label=f"Capability: {row.capability.name}",
                    value=value,
                )
            )
    return contributions
