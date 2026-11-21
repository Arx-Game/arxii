"""Divine intervention as one graded roll (#4349, ADR-4349).

Someone in dire straits calls on a being: the fallen character's own prayer, an ally's prayer
for them, or, at very high favor, the being stepping in by itself when they fall (divine
intercession). All three are the same thing here. The one praying rolls the being's invocation
check at the invocation difficulty (their favor and favor invocation modifiers ease it; botch
immunity on the Faith check category, if staff authored one, floors a botch as on every check),
and the result tier decides the answer:

* Critical Failure: a backfire drawn from the being's intervention pool, landing on the one
  praying.
* Failure: unanswered; an optional authored sign, no aid.
* Partial Success: a lesser answer drawn from the pool, landing on the one in danger.
* Success: a rescue, the lowest-priority affordable miracle with minimum tier Success.
* Critical Success: the bigger miracle, with the Success-tier miracle then a lesser answer as
  fallbacks.

The one praying pays: a rescue and a bigger miracle spend favor (``FavorOutcomeAward`` rows of
kind INTERVENTION_SPEND), a weaker answer leaves favor owed (INTERVENTION_DEBT, paid from base
favor before the earning rate by ``bump_devotion``), and every roll sets a minimum wait
(INTERVENTION_WAIT_HOURS) on the existing cooldown condition. Higher favor softens the owed
favor and the wait. A being ignores a character who is waiting, owes it favor, or is below the
prayer gate (or below 0 favor, by ``DivineInterventionConfig.below_zero_rule``); invoking for a
check bonus is not touched by any of it. A steward's live miracle answer
(``world.worship.live_services``) is a separate path that obeys none of this.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.constants import BOTCH_SUCCESS_LEVEL_MAX
from world.scenes.action_constants import DIFFICULTY_VALUES
from world.worship.constants import (
    ANSWER_FACT_MIN_SUCCESS_LEVEL,
    ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL,
    BelowZeroRule,
    FavorAwardKind,
    InterventionStatus,
)
from world.worship.invocation_services import (
    band_for_points,
    favor_with,
    get_devotion_config,
    invocation_check_type,
    invocation_difficulty,
    is_secret_faith,
    outcome_award,
    partial_success_outcome,
)
from world.worship.models import DevotionStanding
from world.worship.services import (
    bump_devotion,
    get_divine_intervention_config,
    intervention_cooldown_active,
    miracle_ineligibility,
    perform_divine_intervention,
    route_intervention_text,
)
from world.worship.types import (
    FavorSource,
    InterventionCost,
    InterventionResult,
    InvocationDifficulty,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence, ConsequencePool
    from world.checks.types import CheckResult
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome
    from world.worship.models import (
        DevotionConfig,
        DivineInterventionConfig,
        Miracle,
        WorshippedBeing,
    )

#: Result levels of the canonical tiers, read through the answer constants so the intervention
#: roll and an answer's tier table agree on what Partial Success and Success are.
LESSER_LEVEL = ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL
RESCUE_LEVEL = ANSWER_FACT_MIN_SUCCESS_LEVEL
BIGGER_MIRACLE_LEVEL = RESCUE_LEVEL + 1
#: The one level between a botch and a lesser answer: Failure, which gets only a sign.
SIGN_LEVEL = BOTCH_SUCCESS_LEVEL_MAX + 1

_SIGN_WHEEL_TITLE = "{being} answers"


def _name(sheet: CharacterSheet) -> str:
    """The face ``sheet`` presents as, never ``str(sheet)``."""
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        return active_persona_for_sheet(sheet).name
    except Persona.DoesNotExist:
        return sheet.character.db_key


def intercession_being(
    sheet: CharacterSheet, cfg: DivineInterventionConfig
) -> WorshippedBeing | None:
    """The being that steps in for ``sheet`` by itself when she falls, or None.

    Her favor with it must be at or above the divine intercession threshold. Her patron if she
    has one among those beings (a Chosen's patron, never a pact's), otherwise the being she has
    the highest favor with. A character whose only patron comes from a pact rolls against her
    highest-favor being.
    """
    from world.worship.favor_services import chosen_patronages_for  # noqa: PLC0415

    standings = list(
        DevotionStanding.objects.filter(
            character_sheet=sheet, favor__gte=cfg.favor_threshold, being__is_active=True
        )
        .select_related("being")
        .order_by("-favor", "being__name")
    )
    if not standings:
        return None
    for patronage in chosen_patronages_for(sheet):
        for standing in standings:
            if standing.being_id == patronage.being_id:
                return standing.being
    return standings[0].being


def softening_percent(favor: int, cfg: DivineInterventionConfig, config: DevotionConfig) -> int:
    """How much favor softens the owed favor and the wait, as a percent.

    ``debt_softening_high_percent`` at or above the high favor ease threshold, the low percent
    at or above the low one, else 0. The thresholds are Devotion config's favor ease bands.
    """
    if favor >= config.favor_ease_high_threshold:
        return cfg.debt_softening_high_percent
    if favor >= config.favor_ease_low_threshold:
        return cfg.debt_softening_low_percent
    return 0


def soften(amount: int, percent: int) -> int:
    """``amount`` less ``percent`` percent, rounded up to a whole number."""
    return -(-amount * (100 - min(percent, 100)) // 100)


def _refusal_status(
    praying: CharacterSheet, being: WorshippedBeing, cfg: DivineInterventionConfig
) -> tuple[str, str]:
    """(status, reason) when the being will not roll for ``praying``, else ("", "")."""
    standing = DevotionStanding.objects.filter(character_sheet=praying, being=being).first()
    favor = standing.favor if standing is not None else 0
    if intervention_cooldown_active(praying.character):
        return InterventionStatus.WAITING, f"{being.name} is not considering you yet."
    if standing is not None and standing.owed_favor > 0:
        return InterventionStatus.OWED, f"You owe {being.name} {standing.owed_favor} favor."
    if favor < 0 and cfg.below_zero_rule == BelowZeroRule.AUTOMATIC_FAILURE:
        return InterventionStatus.BELOW_ZERO, f"{being.name} turns from you."
    if favor >= 0 and favor < cfg.prayer_favor_gate:
        return InterventionStatus.BELOW_GATE, f"{being.name} does not know you well enough."
    return "", ""


def _difficulty(
    praying: CharacterSheet, being: WorshippedBeing, cfg: DivineInterventionConfig, favor: int
) -> InvocationDifficulty:
    """The roll's difficulty: the invocation difficulty, or the much harder roll below 0."""
    if favor < 0:
        points = DIFFICULTY_VALUES[cfg.below_zero_difficulty]
        return InvocationDifficulty(
            base_points=points,
            base_band=cfg.below_zero_difficulty,
            eases=(),
            points=points,
            band=band_for_points(points),
        )
    return invocation_difficulty(praying, being)


def _roll(
    praying: CharacterSheet,
    being: WorshippedBeing,
    difficulty: InvocationDifficulty,
    scene: Scene | None,
) -> CheckResult:
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    return perform_check_with_modifiers(
        praying.character,
        invocation_check_type(being),
        target_difficulty=difficulty.points,
        specialization=being.tradition.rites_specialization,
        scene=scene,
        extra_traits=activity_skill_terms(MagicActivity.INVOCATION),
    )


def _pool_rows(pool: ConsequencePool | None, outcome: CheckOutcome) -> list:
    """The pool's rows for ``outcome``'s tier, as weighted consequences (parent rows included)."""
    from actions.services import get_effective_consequences  # noqa: PLC0415

    if pool is None:
        return []
    return [row for row in get_effective_consequences(pool) if row.outcome_tier.pk == outcome.pk]


def _draw(  # noqa: PLR0913 - the draw's whole context is keyword data
    *,
    being: WorshippedBeing,
    outcome: CheckOutcome,
    check_result: CheckResult,
    praying: CharacterSheet,
    lands_on: CharacterSheet,
    apply: bool,
    wheel: bool,
    scene: Scene | None,
) -> tuple[Consequence | None, tuple[str, ...]]:
    """Draw one row of the being's pool for ``outcome`` from the roll's own result, no second
    roll, and apply it to ``lands_on`` when ``apply``. Returns the drawn consequence (None when
    the pool has no row for the tier) and the lines of what it did.

    The resolution wheel shows every row of the tier to the one praying when ``wheel`` and
    there is more than one, since ``select_consequence_from_result`` never emits it.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.theater import maybe_emit_resolution_theater  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    rows = _pool_rows(being.intervention_pool, outcome)
    if not rows:
        return None, ()
    if check_result.outcome is None or check_result.outcome.pk != outcome.pk:
        # A lesser answer drawn in place of a miracle reads the Partial Success rows.
        check_result = dataclasses.replace(check_result, outcome=outcome)
    pending = select_consequence_from_result(lands_on.character, check_result, rows)
    drawn = pending.selected_consequence.consequence
    maybe_emit_resolution_theater(
        character=praying.character,
        title=_SIGN_WHEEL_TITLE.format(being=being.name),
        consequences=[row.consequence for row in rows],
        selected=drawn,
        force=wheel and len(rows) > 1,
    )
    if not apply:
        return drawn, ()
    context = ResolutionContext(
        character=lands_on.character,
        target=lands_on.character,
        source_character=praying.character,
        scene=scene,
        outcome_tier=outcome,
    )
    applied = apply_resolution(pending, context)
    return drawn, tuple(effect.description for effect in applied if effect.applied)


def _candidate_miracles(
    *,
    praying: CharacterSheet,
    being: WorshippedBeing,
    trigger: str,
    favor: int,
    cfg: DivineInterventionConfig,
) -> list[Miracle]:
    """The being's affordable miracles for ``trigger``, lowest sort order first."""
    from world.worship.models import Miracle  # noqa: PLC0415

    miracles = (
        Miracle.objects.filter(being=being, intervention_trigger=trigger, is_active=True)
        .select_related("min_outcome_tier", "being")
        .order_by("sort_order", "pk")
    )
    return [
        miracle
        for miracle in miracles
        if not miracle_ineligibility(praying, miracle, favor=favor, on_cooldown=False, cfg=cfg)
    ]


def _miracle_for(candidates: list[Miracle], outcome: CheckOutcome) -> Miracle | None:
    """The miracle ``outcome`` brings: at Critical Success the lowest-priority one whose minimum
    tier is Critical Success, else the lowest-priority one whose minimum tier is Success."""
    level = outcome.success_level

    def minimum(miracle: Miracle) -> int:
        tier = miracle.min_outcome_tier
        return tier.success_level if tier is not None else RESCUE_LEVEL

    if level >= BIGGER_MIRACLE_LEVEL:
        bigger = [m for m in candidates if minimum(m) >= BIGGER_MIRACLE_LEVEL]
        if bigger:
            return bigger[0]
    rescues = [m for m in candidates if minimum(m) <= RESCUE_LEVEL]
    return rescues[0] if rescues else None


def _lesser_tier(outcome: CheckOutcome) -> CheckOutcome:
    """The Partial Success tier a lesser answer in place of a miracle is drawn from. The cost
    stays the rolled tier's (debt and wait rows), and nothing is spent."""
    return partial_success_outcome() or outcome


def _charge(  # noqa: PLR0913 - the cost's context is keyword data
    *,
    praying: CharacterSheet,
    being: WorshippedBeing,
    cost_tier: CheckOutcome,
    spends: bool,
    charges: bool,
    cfg: DivineInterventionConfig,
    config: DevotionConfig,
) -> InterventionCost:
    """Apply the cost of one roll to ``praying`` and return what it came to.

    ``spends`` is true for a rescue or bigger miracle (the only results that spend favor);
    ``charges`` is false for a result that gave nothing (no spend, no debt, only the wait).
    The owed favor and the wait are softened by the favor read before the spend.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.worship.services import COOLDOWN_CONDITION_NAME  # noqa: PLC0415

    standing, _ = DevotionStanding.objects.get_or_create(character_sheet=praying, being=being)
    percent = softening_percent(standing.favor, cfg, config)
    spend = (outcome_award(FavorAwardKind.INTERVENTION_SPEND, cost_tier) or 0) if spends else 0
    base_debt = (outcome_award(FavorAwardKind.INTERVENTION_DEBT, cost_tier) or 0) if charges else 0
    debt = soften(base_debt, percent)
    wait_row = outcome_award(FavorAwardKind.INTERVENTION_WAIT_HOURS, cost_tier)
    wait = soften(wait_row, percent) if wait_row is not None else cfg.cooldown_hours
    if spend and charges:
        bump_devotion(praying, being, -spend, source=FavorSource())
    else:
        spend = 0
    if debt:
        standing.refresh_from_db(fields=["owed_favor"])
        standing.owed_favor += debt
        standing.save(update_fields=["owed_favor"])
    template = ConditionTemplate.objects.filter(name=COOLDOWN_CONDITION_NAME).first()
    if template is not None and wait > 0:
        apply_condition(target=praying.character, condition=template, duration_rounds=wait * 60)
    return InterventionCost(favor_spent=spend, favor_owed=debt, wait_hours=wait)


def _room_text(drawn: Consequence, effects: tuple[str, ...]) -> str:
    """What the room reads of a lesser answer or backfire: its authored text, then the visible
    effects (a condition appearing). Never the roll, the difficulty or anyone's favor."""
    text = _text_of(drawn)
    if not effects:
        return text
    return f"{text} ({'; '.join(effects)})".strip()


def _gm_context(
    *,
    result_outcome: CheckOutcome,
    being: WorshippedBeing,
    praying: CharacterSheet,
    target: CharacterSheet,
    what: str,
) -> str:
    """The GM's line for the prompt: who prayed for whom, the result and what was drawn."""
    who = _name(praying)
    whom = _name(target)
    head = (
        f"{being.name} answered {who}'s prayer for {whom}"
        if praying.pk != target.pk
        else f"{whom}'s god {being.name} answered"
    )
    return f"{head}: {result_outcome.name}; {what}."


def _text_of(consequence: Consequence) -> str:
    """A drawn consequence's authored text: its description, else its label."""
    return consequence.mechanical_description.strip() or consequence.label


def fire_divine_intervention(  # noqa: PLR0913 - one roll, every branch of its result
    praying: CharacterSheet,
    *,
    trigger: str,
    trigger_event: str,
    scene: Scene | None = None,
    being: WorshippedBeing | None = None,
    target: CharacterSheet | None = None,
) -> InterventionResult:
    """Roll one divine intervention for ``target`` (the one in danger) made by ``praying``.

    ``target`` is ``praying`` when None: a prayer for oneself, or divine intercession (``being``
    None picks the being that steps in, see ``intercession_being``). The roll, its cost and the
    wait all belong to ``praying``; miracles and lesser answers land on ``target``, a backfire
    on ``praying``. ``trigger`` picks the miracles that can answer and ``trigger_event`` is
    recorded on a miracle's audit row. Returns what happened in an ``InterventionResult``; when
    nothing rolled its ``status`` says why.

    The refusal checks, the roll and the cost run under a lock on the character's standing
    with the being, so two calls at once cannot both pass the wait and owed-favor checks.
    """
    target = target if target is not None else praying
    if being is None:
        being = intercession_being(praying, get_divine_intervention_config())
    if being is None:
        return InterventionResult(InterventionStatus.NO_BEING, praying, target)
    with transaction.atomic():
        DevotionStanding.objects.select_for_update().filter(
            character_sheet=praying, being=being
        ).first()
        return _intervene(
            praying, target, being, trigger=trigger, trigger_event=trigger_event, scene=scene
        )


def _intervene(  # noqa: PLR0913 - the roll's whole context, keyword-only
    praying: CharacterSheet,
    target: CharacterSheet,
    being: WorshippedBeing,
    *,
    trigger: str,
    trigger_event: str,
    scene: Scene | None,
) -> InterventionResult:
    """The body of ``fire_divine_intervention``, run under its lock."""
    cfg = get_divine_intervention_config()
    config = get_devotion_config()
    status, reason = _refusal_status(praying, being, cfg)
    if status:
        return InterventionResult(status, praying, target, being=being, refusal=reason)
    if invocation_check_type(being) is None:
        return InterventionResult(InterventionStatus.NO_CHECK_TYPE, praying, target, being=being)

    favor = favor_with(praying, being)
    difficulty = _difficulty(praying, being, cfg, favor)
    check_result = _roll(praying, being, difficulty, scene)
    outcome = check_result.outcome
    level = outcome.success_level

    performance = None
    drawn = None
    effects: tuple[str, ...] = ()
    spends = False
    cost_tier = outcome
    if level >= RESCUE_LEVEL:
        candidates = _candidate_miracles(
            praying=praying, being=being, trigger=trigger, favor=favor, cfg=cfg
        )
        miracle = _miracle_for(candidates, outcome)
        if miracle is not None:
            context_text = _gm_context(
                result_outcome=outcome,
                being=being,
                praying=praying,
                target=target,
                what=f"miracle: {miracle.name}",
            )
            performance = perform_divine_intervention(
                target,
                being,
                miracle,
                scene=scene,
                trigger_event=trigger_event,
                outcome_tier=outcome,
                context_text=context_text,
            )
            spends = True
            effects = tuple(
                f"condition applied, {row.condition.name}"
                for row in miracle.condition_applications.select_related("condition")
            )
        else:
            drawn, effects = _draw(
                being=being,
                outcome=_lesser_tier(outcome),
                check_result=check_result,
                praying=praying,
                lands_on=target,
                apply=True,
                wheel=True,
                scene=scene,
            )
    elif level >= LESSER_LEVEL:
        drawn, effects = _draw(
            being=being,
            outcome=outcome,
            check_result=check_result,
            praying=praying,
            lands_on=target,
            apply=True,
            wheel=True,
            scene=scene,
        )
    elif level <= BOTCH_SUCCESS_LEVEL_MAX:
        drawn, effects = _draw(
            being=being,
            outcome=outcome,
            check_result=check_result,
            praying=praying,
            lands_on=praying,
            apply=True,
            wheel=False,
            scene=scene,
        )
    else:
        drawn, _ = _draw(
            being=being,
            outcome=outcome,
            check_result=check_result,
            praying=praying,
            lands_on=praying,
            apply=False,
            wheel=False,
            scene=scene,
        )

    delivered = performance is not None or (drawn is not None and level >= LESSER_LEVEL)
    cost = _charge(
        praying=praying,
        being=being,
        cost_tier=cost_tier,
        spends=spends,
        charges=delivered or level < LESSER_LEVEL,
        cfg=cfg,
        config=config,
    )
    if drawn is not None and performance is None and level != SIGN_LEVEL:
        route_intervention_text(
            praying if level <= BOTCH_SUCCESS_LEVEL_MAX else target,
            _room_text(drawn, effects),
            scene,
            context_text=_gm_context(
                result_outcome=outcome,
                being=being,
                praying=praying,
                target=target,
                what=f"drawn: {drawn.label}",
            ),
        )
    return InterventionResult(
        InterventionStatus.ROLLED,
        praying,
        target,
        being=being,
        difficulty=difficulty,
        outcome=outcome,
        performance=performance,
        drawn=drawn,
        effects=effects,
        cost=cost,
    )


def _difficulty_words(difficulty: InvocationDifficulty) -> str:
    """ "Difficulty Trivial (15): base Daunting 75; Favor 65 (60 or more) -30; ...": each ease
    that applied, so the player sees why the roll was as hard as it was."""
    from world.scenes.action_constants import DifficultyChoice  # noqa: PLC0415

    base = f"base {DifficultyChoice(difficulty.base_band).label} {difficulty.base_points}"
    eases = "; ".join(f"{ease.label} -{ease.points}" for ease in difficulty.eases if ease.points)
    band = DifficultyChoice(difficulty.band).label
    detail = f"{base}; {eases}" if eases else base
    return f"Difficulty {band} ({difficulty.points}): {detail}."


def _cost_words(cost: InterventionCost) -> str:
    spent = f"favor spent {cost.favor_spent}" if cost.favor_spent else "no favor spent"
    owed = f"favor owed {cost.favor_owed}" if cost.favor_owed else "nothing owed"
    return f"{spent}; {owed}; it will not answer again for {cost.wait_hours} hours"


def _answer_head(result: InterventionResult, mode: str) -> str:
    being, outcome = result.being.name, result.outcome.name
    if mode == PRAYER_FOR_ANOTHER:
        return f"{being} answered your prayer for {_name(result.target)} ({outcome})"
    if mode == INTERCESSION:
        return f"{being} stepped in for you ({outcome})"
    return f"{being} answered you ({outcome})"


#: How the one praying came to call: for themselves, for someone else, or the being stepped in.
PRAYER_FOR_SELF = "self"
PRAYER_FOR_ANOTHER = "another"
INTERCESSION = "intercession"


def intervention_lines(result: InterventionResult, *, mode: str = PRAYER_FOR_SELF) -> list[str]:
    """The private lines the one praying reads after ``result`` (system templates, wording for
    staff to confirm): the authored sign on a Failure, then what a lesser answer or backfire
    did, then who answered and what it cost, then how the roll was eased.

    A miracle's or drawn answer's authored text goes to the scene (``route_intervention_text``),
    not here. A result that rolled nothing yields its refusal line, if the player may be told
    one; a Failure with no sign yields nothing.
    """
    if not result.rolled:
        return [result.refusal] if result.refusal else []
    outcome = result.outcome
    if outcome.success_level == SIGN_LEVEL:
        return [_text_of(result.drawn)] if result.drawn is not None else []
    lines = [f"({effect})" for effect in result.effects]
    if outcome.success_level >= LESSER_LEVEL and not result.answered:
        # A Success or Partial Success the being had nothing to answer with (no affordable
        # miracle, no row drawn): it costs its wait, and the player is not told it answered.
        lines.append(
            f"Nothing came of your call on {result.being.name} ({outcome.name}); "
            f"{_cost_words(result.cost)}."
        )
        return lines
    lines.append(f"{_answer_head(result, mode)}; {_cost_words(result.cost)}.")
    if result.difficulty is not None:
        lines.append(_difficulty_words(result.difficulty))
    return lines


def intercession_lines(result: InterventionResult) -> list[str]:
    """What the fallen character reads when the being stepped in by itself."""
    return intervention_lines(result, mode=INTERCESSION)


def prayed_for_you_lines(result: InterventionResult) -> list[str]:
    """What the fallen character reads when someone else prayed for them: who prayed, then what
    landed on them (a miracle's or a lesser answer's effects). Nothing on a Failure, a backfire
    (which landed on the one praying) or a result that gave nothing."""
    landed = result.performance is not None or (
        result.drawn is not None and result.outcome.success_level >= LESSER_LEVEL
    )
    if not landed:
        return []
    being = result.being.name if result.being is not None else "a being"
    lines = [f"{_name(result.praying)} prayed to {being} for you."]
    lines.extend(f"({effect})" for effect in result.effects)
    return lines


def prayer_room_line(
    praying: CharacterSheet, target: CharacterSheet, being: WorshippedBeing
) -> str:
    """The line onlookers read when an ally prays for a fallen character; a secret faith is
    only a call on something."""
    if is_secret_faith(praying, being):
        return f"{_name(praying)} calls on something for {_name(target)}."
    return f"{_name(praying)} prays to {being.name} for {_name(target)}."
