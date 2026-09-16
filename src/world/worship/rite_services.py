"""Performing worship rites (#3777).

A rite is a scene act with a real cost (one Action Point per tier plus a little
social fatigue) and an outcome-tiered payout read from ``WorshipRiteTierAward``:
the same check-then-authored-row-per-outcome shape as the personal anima ritual
(``world.magic.services.anima``). Resonance is granted on every performance;
Devotion favor at most once per rite per game week, so repeating a rite stays
fine for RP and only standing is capped. Tier 3 rites are Ceremonies: their
award is paid by ``world.ceremonies.services.finish_ceremony`` through
``apply_rite_award`` below, never by ``perform_worship_rite``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.worship.constants import (
    BIRTH_FAVOR_REWARD_MULTIPLIER_PERCENT,
    FAVORED_RESONANCE_REWARD_MULTIPLIER_PERCENT,
    FEAST_DAY_REWARD_MULTIPLIER_PERCENT,
    RITE_AP_COST_PER_TIER,
    RITE_SOCIAL_FATIGUE_COST,
    BeingResonanceTier,
    RiteTier,
)
from world.worship.exceptions import (
    RiteActionPointsInsufficient,
    RiteAwardMissing,
    RiteIsCeremony,
    RiteNotAvailable,
    RiteScenePrerequisiteFailed,
)
from world.worship.models import WorshipRite, WorshipRitePerformance, WorshipRiteTierAward

if TYPE_CHECKING:
    from world.ceremonies.models import Ceremony
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome
    from world.worship.models import WorshippedBeing


@dataclass(frozen=True)
class RiteOutcome:
    """What one performance paid, for the action's result line."""

    performance: WorshipRitePerformance
    outcome_name: str
    resonance_granted: int
    favor_granted: int
    favor_capped: bool
    multiplier_percent: int


def rite_ap_cost(rite: WorshipRite) -> int:
    """The AP a rite costs: one per tier (PLACEHOLDER magnitude)."""
    return rite.kind.tier * RITE_AP_COST_PER_TIER


def is_feast_day_today(being: WorshippedBeing) -> bool:
    """Whether the IC calendar sits on one of ``being``'s feast days.

    False (never raises) with no active GameClock, the same graceful skip
    ``is_birth_favored_by`` uses on a bare test database.
    """
    from world.game_clock.services import get_ic_now  # noqa: PLC0415

    ic_now = get_ic_now()
    if ic_now is None:
        return False
    today = ic_now.date()
    return being.feast_days.filter(ic_month=today.month, ic_day=today.day).exists()


def reward_multiplier_percent(character_sheet: CharacterSheet, rite: WorshipRite) -> int:
    """The percent multiplier on a rite's tier award, all PLACEHOLDER magnitudes.

    A FAVORED being resonance pays double (``BeingResonance`` docstring); a
    feast day of the being doubles again; birth favor (``is_birth_favored_by``)
    doubles again. They stack by multiplication.
    """
    from world.worship.services import is_birth_favored_by  # noqa: PLC0415

    percent = 100
    if rite.resonance.tier == BeingResonanceTier.FAVORED:
        percent = percent * FAVORED_RESONANCE_REWARD_MULTIPLIER_PERCENT // 100
    if is_feast_day_today(rite.being):
        percent = percent * FEAST_DAY_REWARD_MULTIPLIER_PERCENT // 100
    if is_birth_favored_by(character_sheet, rite.being):
        percent = percent * BIRTH_FAVOR_REWARD_MULTIPLIER_PERCENT // 100
    return percent


def favor_capped_this_week(character_sheet: CharacterSheet, rite: WorshipRite) -> bool:
    """Whether ``character_sheet`` already earned favor from ``rite`` this game week."""
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    return WorshipRitePerformance.objects.filter(
        character_sheet=character_sheet,
        rite=rite,
        game_week=get_current_game_week(),
        favor_granted__gt=0,
    ).exists()


def apply_rite_award(
    character_sheet: CharacterSheet,
    rite: WorshipRite,
    outcome: CheckOutcome,
    *,
    scene: Scene | None = None,
    ceremony: Ceremony | None = None,
) -> RiteOutcome:
    """Pay a rite's tier award for ``outcome``: the audit row, the resonance
    grant (ledger source WORSHIP_RITE) and the weekly-capped favor bump.

    Shared by a solo performance (``perform_worship_rite``, which rolled the
    check itself) and a tier 3 ceremony (``finish_ceremony``, which passes the
    officiant's Rites roll). Raises ``RiteAwardMissing`` for an unseeded
    (tier, outcome) pair rather than paying 0.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.worship.services import bump_devotion  # noqa: PLC0415

    award = WorshipRiteTierAward.objects.filter(tier=rite.kind.tier, outcome_tier=outcome).first()
    if award is None:
        raise RiteAwardMissing
    percent = reward_multiplier_percent(character_sheet, rite)
    resonance_amount = award.resonance_amount * percent // 100
    capped = favor_capped_this_week(character_sheet, rite)
    favor_amount = 0 if capped else award.favor_amount * percent // 100

    with transaction.atomic():
        performance = WorshipRitePerformance.objects.create(
            character_sheet=character_sheet,
            rite=rite,
            game_week=get_current_game_week(),
            scene=scene,
            ceremony=ceremony,
            outcome_tier=outcome,
            resonance_granted=resonance_amount,
            favor_granted=favor_amount,
        )
        if resonance_amount > 0:
            grant_resonance(
                character_sheet,
                rite.resonance.resonance,
                resonance_amount,
                source=GainSource.WORSHIP_RITE,
                worship_rite_performance=performance,
            )
        if favor_amount > 0:
            bump_devotion(character_sheet, rite.being, favor_amount)
    return RiteOutcome(
        performance=performance,
        outcome_name=outcome.name,
        resonance_granted=resonance_amount,
        favor_granted=favor_amount,
        favor_capped=capped,
        multiplier_percent=percent,
    )


def _scene_participant(scene: Scene, character_sheet: CharacterSheet) -> bool:
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    account = account_for_sheet(character_sheet)
    if account is None:
        return False
    return SceneParticipation.objects.filter(scene=scene, account=account).exists()


def _charge_costs(character_sheet: CharacterSheet, rite: WorshipRite) -> None:
    """One AP per tier and a little social fatigue, charged before the roll.

    A botched rite still cost its performer the effort: the cost is the
    dramatic stake, not a fee for the reward (the anima ritual's philosophy).
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue  # noqa: PLC0415

    pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if pool is None or not pool.spend(rite_ap_cost(rite)):
        raise RiteActionPointsInsufficient
    apply_fatigue(
        character_sheet, ActionCategory.SOCIAL, RITE_SOCIAL_FATIGUE_COST, EffortLevel.MEDIUM
    )


def perform_worship_rite(
    character_sheet: CharacterSheet, rite: WorshipRite, *, scene: Scene
) -> RiteOutcome:
    """Perform a tier 1 or 2 rite in a live scene: pay, roll, be paid.

    The check is the rite's own ``check_type`` with the being's tradition
    specialization (the same modifier the ceremony Rites roll applies), so a
    Shepherd's vigil and a Hollow Flame's vigil roll the same skill through
    different liturgies. Tier 3 rites are ceremonies and are refused here.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415

    if not rite.is_active or not rite.being.is_active:
        raise RiteNotAvailable
    if rite.kind.tier == RiteTier.PERILOUS:
        raise RiteIsCeremony
    if not scene.is_active or not _scene_participant(scene, character_sheet):
        raise RiteScenePrerequisiteFailed

    with transaction.atomic():
        _charge_costs(character_sheet, rite)
        result = perform_check_with_modifiers(
            character_sheet.character,
            rite.check_type,
            specialization=rite.being.tradition.rites_specialization,
            scene=scene,
        )
        return apply_rite_award(character_sheet, rite, result.outcome, scene=scene)
