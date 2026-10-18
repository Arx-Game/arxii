"""Invoking a being's favor before a check (#4333, design 1; ADR-4333-A).

A character with favor above zero calls on a being before a check. The system
rolls an invocation check first, and its outcome tier sets the bonus (a
``FavorOutcomeAward`` row of kind INVOCATION) added to the check that follows,
as a labelled ``ModifierContribution`` of kind FAVOR. Favor is never spent; each
invocation writes a ``FavorInvocation`` row, which is both the weekly counter and
the log. Callers (mission options, scene checks, scene actions) own the check the
bonus lands on and where the lines are delivered.

Difficulty, in points: ``DevotionConfig.base_difficulty`` minus the Chosen ease
(``ChosenFavorConfig.invocation_ease_points``) for an active patronage of the
being, minus the favor ease at the configured thresholds, minus the character's
favor invocation total for the being (``favor_modifier_total``). Never below
Trivial. Eases add (ruling 12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierContribution
from world.mechanics.constants import FAVOR_INVOCATION_CATEGORY_NAME
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    MIN_DIFFICULTY_POINTS,
    DifficultyChoice,
)
from world.worship.constants import FavorAwardKind
from world.worship.exceptions import FavorInvocationRefused
from world.worship.favor_services import active_patronage_of, favor_modifier_total
from world.worship.types import (
    InvocationBonusRow,
    InvocationChoice,
    InvocationDifficulty,
    InvocationEase,
    InvocationOption,
    InvocationOutcome,
    InvocationRequest,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.game_clock.models import GameWeek
    from world.missions.models import MissionInstance
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome
    from world.worship.models import DevotionConfig, FavorInvocation, WorshippedBeing

MSG_NO_FAVOR = "You have no favor with {being} to call on."
MSG_NO_USES = "You have called on {being} {uses} times this week already."
MSG_NOT_CONFIGURED = "Calling on favor is not set up yet; tell staff."
MSG_BEING_INACTIVE = "{being} cannot be called on."
MSG_NO_SUCH_BEING = "There is no such being to call on."
CHOSEN_EASE_LABEL = "You are {being}'s Chosen"
FAVOR_EASE_LABEL = "Favor {favor} ({threshold} or more)"
MODIFIER_EASE_LABEL = "Favor invocation modifiers for {being}"


def get_devotion_config() -> DevotionConfig:
    """Lazy-create the ``DevotionConfig`` singleton (pk=1)."""
    from world.worship.models import DevotionConfig  # noqa: PLC0415

    config = DevotionConfig.objects.cached_singleton()
    if config is None:
        config, _ = DevotionConfig.objects.get_or_create(pk=1)
    return config


def band_for_points(points: int) -> str:
    """The ``DifficultyChoice`` value nearest ``points``; a tie reads as the harder."""
    return min(
        DIFFICULTY_VALUES,
        key=lambda band: (abs(DIFFICULTY_VALUES[band] - points), -DIFFICULTY_VALUES[band]),
    )


def invocation_check_type(being: WorshippedBeing) -> CheckType | None:
    """The being's own invocation check type, else the configured default (ruling 13)."""
    if being.invocation_check_type_id is not None:
        return being.invocation_check_type
    return get_devotion_config().invocation_check_type


def favor_with(sheet: CharacterSheet, being: WorshippedBeing) -> int:
    """The character's current favor with ``being`` (0 with no standing)."""
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    standing = DevotionStanding.objects.filter(character_sheet=sheet, being=being).first()
    return standing.favor if standing is not None else 0


def invocation_difficulty(sheet: CharacterSheet, being: WorshippedBeing) -> InvocationDifficulty:
    """How hard ``sheet``'s invocation check against ``being`` is, with each ease."""
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    config = get_devotion_config()
    base_points = DIFFICULTY_VALUES[config.base_difficulty]
    eases: list[InvocationEase] = []
    if active_patronage_of(sheet, being) is not None:
        eases.append(
            InvocationEase(
                label=CHOSEN_EASE_LABEL.format(being=being.name),
                points=get_chosen_favor_config().invocation_ease_points,
            )
        )
    favor = favor_with(sheet, being)
    if favor >= config.favor_ease_high_threshold:
        eases.append(
            InvocationEase(
                label=FAVOR_EASE_LABEL.format(
                    favor=favor, threshold=config.favor_ease_high_threshold
                ),
                points=config.favor_ease_high_points,
            )
        )
    elif favor >= config.favor_ease_low_threshold:
        eases.append(
            InvocationEase(
                label=FAVOR_EASE_LABEL.format(
                    favor=favor, threshold=config.favor_ease_low_threshold
                ),
                points=config.favor_ease_low_points,
            )
        )
    eases.append(
        InvocationEase(
            label=MODIFIER_EASE_LABEL.format(being=being.name),
            points=favor_modifier_total(sheet, being, FAVOR_INVOCATION_CATEGORY_NAME),
        )
    )
    points = max(base_points - sum(ease.points for ease in eases), MIN_DIFFICULTY_POINTS)
    return InvocationDifficulty(
        base_points=base_points,
        base_band=config.base_difficulty,
        eases=tuple(eases),
        points=points,
        band=band_for_points(points),
    )


def invocation_bonus_table() -> tuple[InvocationBonusRow, ...]:
    """Every outcome tier's invocation bonus, best tier first (0 where no row)."""
    from world.traits.models import CheckOutcome  # noqa: PLC0415
    from world.worship.models import FavorOutcomeAward  # noqa: PLC0415

    amounts = {
        award.outcome_tier_id: award.amount
        for award in FavorOutcomeAward.objects.filter(
            config=get_devotion_config(), kind=FavorAwardKind.INVOCATION
        )
    }
    return tuple(
        InvocationBonusRow(
            outcome_name=outcome.name,
            success_level=outcome.success_level,
            bonus=amounts.get(outcome.pk, 0),
        )
        for outcome in CheckOutcome.objects.order_by("-success_level", "name")
    )


def invocation_bonus_for(outcome: CheckOutcome | None) -> int:
    """The INVOCATION award for ``outcome``; no row (or no outcome) gives no bonus."""
    from world.worship.models import FavorOutcomeAward  # noqa: PLC0415

    if outcome is None:
        return 0
    award = FavorOutcomeAward.objects.filter(
        config=get_devotion_config(), kind=FavorAwardKind.INVOCATION, outcome_tier=outcome
    ).first()
    return award.amount if award is not None else 0


def invocations_used(
    sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> int:
    """How many invocations ``sheet`` has made of ``being`` this game week."""
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.worship.models import FavorInvocation  # noqa: PLC0415

    week = game_week if game_week is not None else get_current_game_week()
    return FavorInvocation.objects.filter(
        character_sheet=sheet, being=being, game_week=week
    ).count()


def invocation_refusal(
    sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> str:
    """The player-facing reason ``sheet`` cannot invoke ``being`` now, or ""."""
    if not being.is_active:
        return MSG_BEING_INACTIVE.format(being=being.name)
    from world.worship.steward_services import stewarded_refusal  # noqa: PLC0415

    refusal = stewarded_refusal(sheet, being)
    if refusal:
        return refusal
    if favor_with(sheet, being) <= 0:
        return MSG_NO_FAVOR.format(being=being.name)
    per_week = get_devotion_config().invocations_per_week
    if invocations_used(sheet, being, game_week=game_week) >= per_week:
        return MSG_NO_USES.format(being=being.name, uses=per_week)
    if invocation_check_type(being) is None:
        return MSG_NOT_CONFIGURED
    return ""


def check_can_invoke(sheet: CharacterSheet, being: WorshippedBeing) -> None:
    """Raise ``FavorInvocationRefused`` with the reason when ``sheet`` cannot invoke."""
    refusal = invocation_refusal(sheet, being)
    if refusal:
        raise FavorInvocationRefused(refusal)


def find_being_to_invoke(sheet: CharacterSheet, name: str) -> WorshippedBeing | None:
    """The being a typed name means, for telnet: one the character holds a standing
    with first (exact name, then a name that starts with it), else any being with
    exactly that name, so the refusal can name it."""
    from world.worship.models import DevotionStanding, WorshippedBeing  # noqa: PLC0415

    name = name.strip()
    if not name:
        return None
    standings = DevotionStanding.objects.filter(character_sheet=sheet).select_related("being")
    exact = standings.filter(being__name__iexact=name).first()
    if exact is not None:
        return exact.being
    prefixed = standings.filter(being__name__istartswith=name).order_by("being__name").first()
    if prefixed is not None:
        return prefixed.being
    return WorshippedBeing.objects.filter(name__iexact=name).first()


def resolve_invocation_choice(sheet: CharacterSheet, choice: InvocationChoice) -> InvocationRequest:
    """Turn a request's or command's Call on favor choice into a checked request.

    Raises ``FavorInvocationRefused`` when the being does not exist or the
    character cannot invoke it now. The invocation rolls later, with its check.
    """
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    being = WorshippedBeing.objects.filter(pk=choice.being_id).first()
    if being is None:
        raise FavorInvocationRefused(MSG_NO_SUCH_BEING)
    check_can_invoke(sheet, being)
    return InvocationRequest(being=being, player_line=choice.player_line.strip())


def invocation_options(sheet: CharacterSheet) -> list[InvocationOption]:
    """Every being ``sheet`` holds a standing with, for the Call on favor picker.

    A being the character cannot invoke now is listed with the reason, so the
    picker can show it greyed. Ordered by favor, highest first.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    week = get_current_game_week()
    per_week = get_devotion_config().invocations_per_week
    options: list[InvocationOption] = []
    standings = (
        DevotionStanding.objects.filter(character_sheet=sheet, being__is_active=True)
        .select_related("being")
        .order_by("-favor", "being__name")
    )
    for standing in standings:
        being = standing.being
        refusal = invocation_refusal(sheet, being, game_week=week)
        used = invocations_used(sheet, being, game_week=week)
        options.append(
            InvocationOption(
                being=being,
                favor=standing.favor,
                difficulty=invocation_difficulty(sheet, being) if standing.favor > 0 else None,
                uses_left=max(per_week - used, 0),
                uses_per_week=per_week,
                refusal=refusal,
            )
        )
    return options


def is_secret_faith(sheet: CharacterSheet, being: WorshippedBeing) -> bool:
    """True when ``being`` is the hidden second being on the character's declaration."""
    from world.worship.models import WorshipDeclaration  # noqa: PLC0415

    declaration = WorshipDeclaration.objects.filter(character_sheet=sheet).first()
    if declaration is None:
        return False
    return declaration.secret_being_id == being.pk and declaration.public_being_id != being.pk


def invocation_lines(
    *, actor_name: str, being: WorshippedBeing, player_line: str, outcome_name: str, secret: bool
) -> tuple[str, str, str]:
    """The (public call line, private call line, outcome line) strings (design 1).

    The mission log, the room and telnet use exactly these. A secret faith's
    public call line names no being and omits the player line; the acting player
    still sees their own line.
    """
    line = player_line.strip()
    private = (
        f"{actor_name} calls on {being.name}: {line}"
        if line
        else f"{actor_name} calls on {being.name}."
    )
    public = f"{actor_name} calls on something." if secret else private
    return public, private, f"{actor_name}'s invocation: {outcome_name}."


def invoke_favor(  # noqa: PLR0913 - the check's context is co-equal keyword data
    sheet: CharacterSheet,
    being: WorshippedBeing,
    *,
    actor_name: str,
    player_line: str = "",
    scene: Scene | None = None,
    mission_instance: MissionInstance | None = None,
    scene_action_request: SceneActionRequest | None = None,
) -> InvocationOutcome:
    """Roll ``sheet``'s invocation check against ``being`` and record it.

    Raises ``FavorInvocationRefused`` when favor is not above zero, the week's
    invocations are used, or no check type is configured. The check is
    ``perform_check_with_modifiers`` with the being's (or the default) invocation
    check type and the being's tradition specialization, at the difficulty from
    ``invocation_difficulty``; ordinary check modifiers apply. Favor is unchanged.
    ``actor_name`` is the presenting persona's name, which the lines carry.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415
    from world.worship.models import FavorInvocation  # noqa: PLC0415

    check_can_invoke(sheet, being)
    check_type = invocation_check_type(being)
    difficulty = invocation_difficulty(sheet, being)
    with transaction.atomic():
        result = perform_check_with_modifiers(
            sheet.character,
            check_type,
            target_difficulty=difficulty.points,
            specialization=being.tradition.rites_specialization,
            scene=scene,
            extra_traits=activity_skill_terms(MagicActivity.INVOCATION),
        )
        bonus = invocation_bonus_for(result.outcome)
        invocation = FavorInvocation.objects.create(
            character_sheet=sheet,
            being=being,
            game_week=get_current_game_week(),
            outcome_tier=result.outcome,
            bonus=bonus,
            player_line=player_line.strip(),
            scene=scene,
            mission_instance=mission_instance,
            scene_action_request=scene_action_request,
        )
    contribution = invocation_contribution(invocation)
    public, private, outcome_line = invocation_lines(
        actor_name=actor_name,
        being=being,
        player_line=invocation.player_line,
        outcome_name=result.outcome_name,
        secret=is_secret_faith(sheet, being),
    )
    return InvocationOutcome(
        invocation=invocation,
        difficulty=difficulty,
        check_result=result,
        contribution=contribution,
        call_line=public,
        private_call_line=private,
        outcome_line=outcome_line,
    )


def invocation_contribution(invocation: FavorInvocation) -> ModifierContribution | None:
    """The labelled FAVOR line a recorded invocation adds to its check, or None
    when its tier gives no bonus."""
    if not invocation.bonus:
        return None
    being, outcome = invocation.being.name, invocation.outcome_tier.name
    return ModifierContribution(
        source_kind=ModifierSourceKind.FAVOR,
        source_label=f"{being}'s favor (invocation: {outcome})",
        value=invocation.bonus,
    )


def difficulty_label(points: int) -> str:
    """ "30, Easy": the points and the nearest band's label, for the picker and telnet."""
    return f"{points}, {DifficultyChoice(band_for_points(points)).label}"
