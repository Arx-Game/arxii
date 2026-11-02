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

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from django.db import transaction

from world.worship.constants import (
    BIRTH_FAVOR_REWARD_MULTIPLIER_PERCENT,
    FAVORED_RESONANCE_REWARD_MULTIPLIER_PERCENT,
    FEAST_DAY_REWARD_MULTIPLIER_PERCENT,
    RITE_AP_COST_PER_TIER,
    RITE_SOCIAL_FATIGUE_COST,
    BeingResonanceTier,
    PledgeCreditSource,
    RiteTier,
)
from world.worship.exceptions import (
    RiteActionPointsInsufficient,
    RiteAwardMissing,
    RiteGiftIsPartOfTheBody,
    RiteIsCeremony,
    RiteNotAvailable,
    RiteScenePrerequisiteFailed,
)
from world.worship.models import WorshipRite, WorshipRitePerformance, WorshipRiteTierAward

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia_extensions.models import RoomProfile
    from world.ceremonies.models import Ceremony
    from world.ceremonies.services import ItemReading
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import ModifierContribution
    from world.game_clock.models import GameWeek
    from world.items.models import ItemInstance
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome
    from world.worship.models import PledgeDetails, WorshippedBeing


@dataclass(frozen=True)
class RiteOutcome:
    """What one performance paid, for the action's result line."""

    performance: WorshipRitePerformance
    outcome_name: str
    resonance_granted: int
    favor_granted: int
    favor_capped: bool
    multiplier_percent: int
    consecration_bonus_percent: int = 0
    #: Items given up during the rite (#4530) and the ease they gave its roll.
    items_given: tuple[str, ...] = ()
    items_ease: int = 0
    #: How many given items meant something but did not count (past the rite's item limit
    #: or the week's sacrifice limit).
    items_uncounted: int = 0


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


def favor_capped_this_week(
    character_sheet: CharacterSheet, rite: WorshipRite, *, game_week: GameWeek | None = None
) -> bool:
    """Whether ``character_sheet`` already earned favor from ``rite`` this game week."""
    if game_week is None:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

        game_week = get_current_game_week()
    return WorshipRitePerformance.objects.filter(
        character_sheet=character_sheet,
        rite=rite,
        game_week=game_week,
        favor_granted__gt=0,
    ).exists()


def award_for(rite: WorshipRite, outcome: CheckOutcome) -> WorshipRiteTierAward:
    """The (tier, outcome) award row, or ``RiteAwardMissing``: a content gap is
    raised rather than paid as 0 (the AnimaRitualBudgetAward convention)."""
    award = WorshipRiteTierAward.objects.filter(tier=rite.kind.tier, outcome_tier=outcome).first()
    if award is None:
        raise RiteAwardMissing
    return award


def require_complete_award_table(rite: WorshipRite) -> None:
    """Raise ``RiteAwardMissing`` unless every CheckOutcome has a row for the rite's tier.

    Called BEFORE a rite charges anything: the cost spend and the fatigue mutate
    identity-mapped rows in place, and a rollback after them would restore the
    database while the cached instances kept the spent values (ADR-0008). So
    the only content-gap raise happens while nothing has been written yet.
    """
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    expected = set(CheckOutcome.objects.values_list("pk", flat=True))
    have = set(
        WorshipRiteTierAward.objects.filter(tier=rite.kind.tier).values_list(
            "outcome_tier_id", flat=True
        )
    )
    if expected - have:
        raise RiteAwardMissing


def apply_rite_award(  # noqa: PLR0913 - the settlement's inputs are keyword-only and distinct
    character_sheet: CharacterSheet,
    rite: WorshipRite,
    outcome: CheckOutcome,
    *,
    scene: Scene | None = None,
    ceremony: Ceremony | None = None,
    award: WorshipRiteTierAward | None = None,
) -> RiteOutcome:
    """Pay a rite's tier award for ``outcome``: the audit row, the resonance
    grant (ledger source WORSHIP_RITE) and the weekly-capped favor bump.

    Shared by a solo performance (``perform_worship_rite``, which rolled the
    check itself) and a tier 3 ceremony (``finish_ceremony``, which passes the
    officiant's Rites roll and the ``award`` row it already resolved so a
    content gap surfaces before the ceremony's honors are written). Raises
    ``RiteAwardMissing`` for an unseeded (tier, outcome) pair rather than
    paying 0.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.worship.consecration_services import (  # noqa: PLC0415
        grow_consecration,
        sites_of,
    )
    from world.worship.services import bump_devotion  # noqa: PLC0415
    from world.worship.types import FavorSource  # noqa: PLC0415

    if award is None:
        award = award_for(rite, outcome)
    week = get_current_game_week()
    room_profile = _room_profile_for(scene=scene, ceremony=ceremony)
    # #3778: a shrine or temple of the rite's own being adds its tier bonus; the
    # two stack by addition, and the performance then consecrates them further.
    sites = sites_of(room_profile, rite.being)
    site_bonus = sites.bonus_percent()
    percent = reward_multiplier_percent(character_sheet, rite) * (100 + site_bonus) // 100
    resonance_amount = award.resonance_amount * percent // 100
    capped = favor_capped_this_week(character_sheet, rite, game_week=week)
    favor_amount = 0 if capped else award.favor_amount * percent // 100

    with transaction.atomic():
        performance = WorshipRitePerformance.objects.create(
            character_sheet=character_sheet,
            rite=rite,
            game_week=week,
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
            # #4333: the earning rate scales the award; record what was credited.
            favor_amount = bump_devotion(
                character_sheet,
                rite.being,
                favor_amount,
                source=FavorSource(kind=PledgeCreditSource.RITE, rite_performance=performance),
            ).credited
            performance.favor_granted = favor_amount
            performance.save(update_fields=["favor_granted"])
        grow_consecration(sites, rite)
    return RiteOutcome(
        performance=performance,
        outcome_name=outcome.name,
        resonance_granted=resonance_amount,
        favor_granted=favor_amount,
        favor_capped=capped,
        multiplier_percent=percent,
        consecration_bonus_percent=site_bonus,
    )


def _room_profile_for(*, scene: Scene | None, ceremony: Ceremony | None) -> RoomProfile | None:
    """Where a performance happened: the ceremony's room, else the scene's."""
    if ceremony is not None:
        return ceremony.location
    if scene is not None and scene.location is not None:
        return scene.location
    return None


def scene_participant(scene: Scene, character_sheet: CharacterSheet) -> bool:
    """The roster-tenure participation check ``magic.services.anima`` and
    ``conditions.services`` each keep privately; this one reuses the public
    ``account_for_sheet`` walk rather than copying theirs."""
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


@dataclass(frozen=True)
class RiteGift:
    """One item offered during a rite, read before it is given up (#4530)."""

    item: ItemInstance
    reading: ItemReading
    counted: bool


@dataclass(frozen=True)
class RiteGifts:
    """The items offered during a rite: what each meant, which counted, and the ease they
    give the rite's roll (``rite_ease_per_point`` per meaning point, at most
    ``rite_items_counted`` items, within the week's sacrifice limit)."""

    gifts: tuple[RiteGift, ...] = ()
    ease: int = 0
    pledge: PledgeDetails | None = None

    @property
    def eased_by_request(self) -> bool:
        return any(g.counted and g.reading.request is not None for g in self.gifts)

    def contributions(self) -> list[ModifierContribution]:
        from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
        from world.checks.types import ModifierContribution  # noqa: PLC0415

        if self.ease <= 0:
            return []
        names = ", ".join(str(g.item) for g in self.gifts if g.counted)
        return [
            ModifierContribution(
                source_kind=ModifierSourceKind.FAVOR,
                source_label=f"Given up in the rite: {names}",
                value=self.ease,
            )
        ]


def read_rite_gifts(
    sheet: CharacterSheet,
    rite: WorshipRite,
    items: Sequence[ItemInstance],
    *,
    closing_of: PledgeDetails | None = None,
) -> RiteGifts:
    """Read the items offered during ``rite`` (#4530, #4462 section 6.4).

    An item given up during a rite does not roll its own sacrifice check: its meaning points
    (doubled for a favored facet, as at a shrine) ease the rite's roll instead. At most
    ``DevotionConfig.rite_items_counted`` items count, and each counted item uses one of the
    week's sacrifice slots. A matching request fills as at a shrine: the rite's own, and for a
    pledge's closing rite (``closing_of``) the pledge's too, until its quantity is filled.
    """
    from world.ceremonies.services import favored_facets_by_item, read_item  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415
    from world.worship.pledge_services import open_pledge_for  # noqa: PLC0415
    from world.worship.request_services import (  # noqa: PLC0415
        assign_requests,
        closing_rite_requests,
        given_counts,
    )
    from world.worship.sacrifice_services import sacrifice_slots_left  # noqa: PLC0415

    if not items:
        return RiteGifts()
    from world.items.services.natural_weapons import is_natural_weapon  # noqa: PLC0415

    if any(is_natural_weapon(item) for item in items):
        raise RiteGiftIsPartOfTheBody
    config = get_devotion_config()
    pledge = closing_of
    if pledge is None:
        pledge = open_pledge_for(sheet)
        if pledge is not None and pledge.pledge.being_id != rite.being_id:
            pledge = None
    rows = (
        closing_rite_requests(closing_of)
        if closing_of is not None
        else list(rite.requested_items.select_related("item_template", "facet").order_by("pk"))
    )
    filled = given_counts(rows, pledge)
    assigned = assign_requests(rows, items, filled=filled, config=config)
    facets = favored_facets_by_item(rite.being, list(items))
    slots = sacrifice_slots_left(sheet, rite.being)
    room = min(config.rite_items_counted, slots)
    gifts: list[RiteGift] = []
    ease = 0
    for item in items:
        reading = read_item(
            item,
            sheet,
            facet=facets.get(item.pk),
            being=rite.being,
            request=assigned.get(item.pk),
        )
        counted = reading.effective_points > 0 and room > 0
        if counted:
            room -= 1
            ease += reading.effective_points * config.rite_ease_per_point
        gifts.append(RiteGift(item=item, reading=reading, counted=counted))
    return RiteGifts(gifts=tuple(gifts), ease=ease, pledge=pledge)


def give_up_rite_gifts(
    sheet: CharacterSheet,
    rite: WorshipRite,
    gifts: RiteGifts,
) -> tuple[str, ...]:
    """Take the offered items out of play and record each as an offering (#4530): the pool
    grant and the signals are the same as a sacrifice's, and there is no roll of its own."""
    from world.ceremonies.models import CeremonyOffering  # noqa: PLC0415
    from world.ceremonies.services import give_up_item, write_offering_signals  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    persona = active_persona_for_sheet(sheet)
    week = get_current_game_week()
    names: list[str] = []
    for gift in gifts.gifts:
        offered = give_up_item(
            gift.item,
            rite.being,
            reading=gift.reading,
            counted=gift.counted,
            granted_by=sheet,
            reason=f"rite:{rite.name}",
        )
        offering = CeremonyOffering.objects.create(
            being=rite.being,
            pledge_details=gifts.pledge,
            facet=gift.reading.facet,
            item_name=offered.name,
            item_value=offered.value,
            item_legend_value=offered.legend_value,
            worship_grant=offered.worship_grant,
            offered_by=persona,
            game_week=week,
            counted=gift.counted,
        )
        write_offering_signals(offering, gift.reading)
        names.append(offered.name)
    return tuple(names)


def perform_worship_rite(  # noqa: PLR0913 - the rite's context is keyword-only and distinct
    character_sheet: CharacterSheet,
    rite: WorshipRite,
    *,
    scene: Scene,
    pay_award: bool = True,
    offered_items: Sequence[ItemInstance] = (),
    closing_of: PledgeDetails | None = None,
) -> RiteOutcome:
    """Perform a tier 1 or 2 rite in a live scene: pay, roll, be paid.

    The check is the rite's own ``check_type`` with the being's tradition
    specialization (the same modifier the ceremony Rites roll applies), so a
    Shepherd's vigil and a Hollow Flame's vigil roll the same skill through
    different liturgies. Tier 3 rites are ceremonies and are refused here.

    ``pay_award=False`` (#4333 slice 2) is a pledge's closing rite: the costs,
    the roll and the ``WorshipRitePerformance`` row are kept, and the rite's own
    award is not paid; the pledge pays its closing award instead.

    ``offered_items`` (#4530) are items the performer gives up during the rite. They ease
    the rite's roll by their meaning (``read_rite_gifts``) and are taken out of play after
    it rolls; a roll a requested item eased cannot come out as a Critical Failure.
    ``closing_of`` is the pledge a closing rite closes, whose requests the items may fill.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415
    from world.worship.sacrifice_services import lift_botch  # noqa: PLC0415

    if not rite.is_active or not rite.being.is_active:
        raise RiteNotAvailable
    if rite.kind.tier == RiteTier.PERILOUS:
        raise RiteIsCeremony
    if not scene.is_active or not scene_participant(scene, character_sheet):
        raise RiteScenePrerequisiteFailed
    require_complete_award_table(rite)
    gifts = read_rite_gifts(character_sheet, rite, offered_items, closing_of=closing_of)

    with transaction.atomic():
        _charge_costs(character_sheet, rite)
        result = perform_check_with_modifiers(
            character_sheet.character,
            rite.check_type,
            specialization=rite.being.tradition.rites_specialization,
            scene=scene,
            extra_traits=activity_skill_terms(MagicActivity.WORSHIP_RITE),
            extra_contributions=gifts.contributions() or None,
        )
        outcome = lift_botch(result.outcome) if gifts.eased_by_request else result.outcome
        given = give_up_rite_gifts(character_sheet, rite, gifts)
        if not pay_award:
            rite_outcome = record_unpaid_performance(character_sheet, rite, outcome, scene=scene)
        else:
            rite_outcome = apply_rite_award(character_sheet, rite, outcome, scene=scene)
        if not given:
            return rite_outcome
        uncounted = sum(1 for g in gifts.gifts if g.reading.effective_points > 0 and not g.counted)
        return replace(
            rite_outcome, items_given=given, items_ease=gifts.ease, items_uncounted=uncounted
        )


def record_unpaid_performance(
    character_sheet: CharacterSheet, rite: WorshipRite, outcome: CheckOutcome, *, scene: Scene
) -> RiteOutcome:
    """Record a performance that pays no award (a pledge's closing rite, #4333).

    The row keeps the rite's place in the log and the outcome the pledge reads;
    its resonance and favor stay 0, so it never counts toward the rite's weekly
    favor cap.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    performance = WorshipRitePerformance.objects.create(
        character_sheet=character_sheet,
        rite=rite,
        game_week=get_current_game_week(),
        scene=scene,
        outcome_tier=outcome,
    )
    return RiteOutcome(
        performance=performance,
        outcome_name=outcome.name,
        resonance_granted=0,
        favor_granted=0,
        favor_capped=False,
        multiplier_percent=100,
    )
