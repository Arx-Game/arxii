"""Resonance currency service functions: grant, imbue, and pull (Spec A §3.1/3.2/5.4/7.4)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import dataclasses
from decimal import Decimal
import logging
import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import (
    ACCELERATED_GAIN_SOURCES,
    AFFINITY_PRIMAL,
    AFFINITY_RATE_EXEMPT_SOURCES,
    GAIN_BONUS_CALLER_ROLLED_SOURCES,
    GAIN_BONUS_EXEMPT_SOURCES,
    EffectKind,
    GainSource,
    TargetKind,
)
from world.magic.exceptions import (
    CovenantRoleNotEngagedError,
    InvalidImbueAmount,
    MagicError,
    NoMatchingWornFacetItemsError,
    PullValidationError,
    ResonanceInsufficient,
)
from world.magic.models import (
    CharacterAnima,
    CharacterResonance,
    IntensityTier,
    ResonanceGrant,
    Thread,
    ThreadCrossingThreshold,
    ThreadLevelUnlock,
)
from world.magic.services.kindled_math import scale_by_kindled_boost, stronger_marks
from world.magic.services.pull_effects import get_pull_effects_for_thread
from world.magic.services.resonance_checks import (
    FULL_WORTH_PERCENT,
    act_stat,
    roll_gain_bonus,
    roll_spend_worth,
)
from world.magic.services.thread_rows import payer_level_read
from world.magic.services.threads import (
    cap_exceeded_error,
    compute_anchor_cap,
    compute_effective_cap,
    compute_level_cap,
    get_imbue_cost_multiplier,
    get_pull_cost,
    is_thread_crossing_level,
    pull_cost_totals,
    pull_resonance_costs,
    recompute_max_health_with_threads,
    relationship_side_from_row,
    thread_level_multiplier,
    thread_rung,
)
from world.magic.types import (
    PayerOption,
    PullPreviewResult,
    ResolvedPullEffect,
    ResonancePullResult,
    ThreadImbueResult,
    ThreadPayerPreview,
)
from world.magic.types.pull import pull_payer
from world.magic.types.resonance_checks import NO_GAIN_BONUS, GainBonus
from world.progression.services.dev_cost import dp_cost_for_step

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.action_points.models import ActionPointPool
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.distinctions.models import CharacterDistinction
    from world.items.models import ItemFacet, Mantle
    from world.magic.models import (
        DramaticMomentTag,
        EntryFlourishRecord,
        KindledStrengthTier,
        KindlingSituation,
        PoseEndorsement,
        Reflection,
        Resonance as ResonanceModel,
        SanctumDetails,
        SceneEntryEndorsement,
        SettlingRite,
        StylePresentationEndorsement,
        Technique,
    )
    from world.magic.models.power_config import CapabilityPowerConfig
    from world.magic.models.threads import ThreadPullEffect
    from world.magic.types import PullActionContext
    from world.magic.types.burn import BurnValuation
    from world.missions.models import MissionDeedRewardLine
    from world.projects.models import Project
    from world.relationships.models import CharacterRelationship, RelationshipCapstone
    from world.traits.models import Trait
    from world.worship.models import WorshipRitePerformance

logger = logging.getLogger(__name__)


# =============================================================================
# Phase 11 — Earn / Spend services (Spec A §3.1, §3.2, §3.6, §7.4)
# =============================================================================


@transaction.atomic
def grant_resonance(  # noqa: PLR0913
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    amount: int,
    *,
    source: str,
    pose_endorsement: PoseEndorsement | None = None,
    scene_entry_endorsement: SceneEntryEndorsement | None = None,
    room_profile: RoomProfile | None = None,
    staff_account: AccountDB | None = None,
    outfit_item_facet: ItemFacet | None = None,
    sanctum_details: SanctumDetails | None = None,
    project: Project | None = None,
    entry_flourish: EntryFlourishRecord | None = None,
    dramatic_moment: DramaticMomentTag | None = None,
    style_presentation_endorsement: StylePresentationEndorsement | None = None,
    mission_deed_reward_line: MissionDeedRewardLine | None = None,
    source_character_distinction: CharacterDistinction | None = None,
    worship_rite_performance: WorshipRitePerformance | None = None,
    kindling_situation: KindlingSituation | None = None,
    settling_rite: SettlingRite | None = None,
    reflection: Reflection | None = None,
    deed_label: str | None = None,
    ledger_out: list[ResonanceGrant] | None = None,
    act_stat: Trait | None = None,
    gain_bonus: GainBonus | None = None,
) -> CharacterResonance:
    """Atomically grant resonance AND write the ResonanceGrant ledger row.

    Validates that the typed source kwarg matches the discriminator. When
    ``source`` is one of ``ACCELERATED_GAIN_SOURCES`` (ADR-0041 — the
    perception/presence gain sources), ``amount`` is scaled up by the
    character's summed distinction earn-rate bonus for ``resonance`` before
    it is written; authored/system sources (including DISTINCTION itself)
    are never accelerated. After that, unless ``source`` is in
    ``AFFINITY_RATE_EXEMPT_SOURCES``, ``amount`` is scaled by the earn rate of the
    resonance's own affinity (#5231), to at least 1. Last comes the bonus resonance check
    (#5308): the amount grows by the percent the check's result is worth, and the row records
    the outcome and the percent. Sources split three ways (``GAIN_BONUS_*_SOURCES``): an exempt
    source never rolls, a rolled source rolls here (once for this call), and a caller-rolled
    source pays several resonances from one act, so its caller rolls once per affinity and
    passes the result as ``gain_bonus``. The ``ResonanceGrant`` row records the scaled amount.

    Args:
        character_sheet: The character receiving resonance.
        resonance: The Resonance being granted.
        amount: Positive integer amount to grant.
        source: GainSource discriminator (keyword-only).
        pose_endorsement: Required for POSE_ENDORSEMENT source.
        scene_entry_endorsement: Required for SCENE_ENTRY source.
        room_profile: Required for ROOM_RESIDENCE source.
        staff_account: Optional for STAFF_GRANT source (nullable by design).
        outfit_item_facet: Required for OUTFIT_TRICKLE source.
        sanctum_details: Required for SANCTUM_WEAVING / SANCTUM_OWNER_BONUS (Plan 4 §F).
        project: Required for PROJECT_CONTRIBUTION (Plan 1+).
        entry_flourish: Required for ENTRY_FLOURISH source.
        dramatic_moment: Required for DRAMATIC_MOMENT source.
        style_presentation_endorsement: Required for STYLE_PRESENTATION source.
        mission_deed_reward_line: Required for MISSION_REWARD source (#1737).
        source_character_distinction: Required for DISTINCTION source (#1834).
        worship_rite_performance: Required for WORSHIP_RITE source (#3777).
        kindling_situation: Required for KINDLED_DEED source (#5124); the authored situation
            that held.
        settling_rite: Required for EMBRACED_DEED (#5124) and SUCCUMBED (#5177); the rite that
            grew the deed or took the Mire.
        reflection: Required for EMBRACED_DEED and SUCCUMBED; the reflection the rite applied.
        deed_label: What the character did, in her own words, recorded on a KINDLED_DEED
            grant (#5124) or a MARKED_ACT grant (#5327, the recorded act's label); None for
            every other source.
        ledger_out: When given, the ``ResonanceGrant`` row this call writes is appended to it,
            for a caller that needs the ledger row as well as the updated resonance.
        act_stat: The stat of the roll the act itself made, which replaces the bonus check's
            stat for a rolled source. None rolls the stat staff set for the source.
        gain_bonus: A bonus check result the caller already rolled for this affinity. Required
            for a caller-rolled source once the bonus check is configured, optional for a
            rolled source (a caller paying several resonances rolls once per affinity), and
            refused for an exempt source.

    Returns:
        The updated CharacterResonance instance.

    Raises:
        InvalidImbueAmount: If amount <= 0.
        ValueError: If source/kwarg shape is invalid.
    """
    if amount <= 0:
        msg = "Resonance grant amount must be positive."
        raise InvalidImbueAmount(msg)

    _validate_grant_source_shape(
        source,
        room_profile=room_profile,
        pose_endorsement=pose_endorsement,
        scene_entry_endorsement=scene_entry_endorsement,
        outfit_item_facet=outfit_item_facet,
        sanctum_details=sanctum_details,
        project=project,
        entry_flourish=entry_flourish,
        dramatic_moment=dramatic_moment,
        style_presentation_endorsement=style_presentation_endorsement,
        mission_deed_reward_line=mission_deed_reward_line,
        source_character_distinction=source_character_distinction,
        worship_rite_performance=worship_rite_performance,
        kindling_situation=kindling_situation,
        settling_rite=settling_rite,
        reflection=reflection,
    )

    if source in ACCELERATED_GAIN_SOURCES:
        from world.magic.services.distinction_resonance import (  # noqa: PLC0415
            distinction_earn_rate_for,
        )

        earn_rate_bonus = distinction_earn_rate_for(character_sheet, resonance)
        if earn_rate_bonus > 0:
            amount = int(amount * (1 + earn_rate_bonus / Decimal(100)))

    if source not in AFFINITY_RATE_EXEMPT_SOURCES:
        # The resonance earned sets how fast it grows (#5231). A deed worth at least 1 is never
        # scaled down to nothing, so its ledger row always exists.
        scaled = amount * resonance.affinity.earn_rate_percent // 100
        amount = max(scaled, 1)

    # The bonus resonance check grows the amount last, so the earn rates it multiplies are
    # already in (#5308). Resolved before any write, so a refused call leaves nothing behind.
    gain_bonus = _resolve_gain_bonus(
        character_sheet, resonance, source, act_stat=act_stat, gain_bonus=gain_bonus
    )
    amount += amount * gain_bonus.percent // 100

    # Peek, don't read: character_sheet.cached_resonances would force a query
    # when cold (the common case for a grant -- unlike Task 2's interaction
    # relations, a grant isn't usually preceded by something else that already
    # warmed this sheet's resonance cache in the same request), defeating the
    # point of this optimization. A cold cache re-queries correctly on next
    # real access regardless, so there's nothing to lose by skipping the
    # mutation below when nothing is cached yet. Peeking (rather than reading)
    # also sidesteps the double-count trap: CharacterResonance.objects.
    # get_or_create() and cr.save() both call Model.save(), which (via
    # RelatedCacheClearingMixin) clears character_sheet.cached_resonances as a
    # side effect of their OWN write -- reading the property again afterward
    # would silently re-query (already including the just-created row) and
    # double-count it on append.
    cached_resonances = character_sheet.__dict__.get("cached_resonances")
    cr, created = CharacterResonance.objects.get_or_create(
        character_sheet=character_sheet,
        resonance=resonance,
        defaults={"balance": 0, "lifetime_earned": 0},
    )
    cr.balance += amount
    cr.lifetime_earned += amount
    cr.save(update_fields=["balance", "lifetime_earned"])
    if created and cached_resonances is not None:
        character_sheet.cached_resonances = [*cached_resonances, cr]

    grant = ResonanceGrant.objects.create(
        character_sheet=character_sheet,
        resonance=resonance,
        amount=amount,
        source=source,
        source_room_profile=room_profile,
        source_staff_account=staff_account,
        source_pose_endorsement=pose_endorsement,
        source_scene_entry_endorsement=scene_entry_endorsement,
        outfit_item_facet=outfit_item_facet,
        source_sanctum_details=sanctum_details,
        source_project=project,
        source_entry_flourish=entry_flourish,
        source_dramatic_moment=dramatic_moment,
        source_style_presentation_endorsement=style_presentation_endorsement,
        source_mission_deed_reward_line=mission_deed_reward_line,
        source_character_distinction=source_character_distinction,
        source_worship_rite_performance=worship_rite_performance,
        source_kindling_situation=kindling_situation,
        deed_label=deed_label,
        source_settling_rite=settling_rite,
        source_reflection=reflection,
        bonus_outcome=gain_bonus.outcome,
        bonus_percent=gain_bonus.percent,
    )
    ledger = [] if ledger_out is None else ledger_out
    ledger.append(grant)
    # #4333 slice 2: a grant of a resonance the character's pledged being values
    # is a deed, and earns favor toward the open pledge.
    from world.worship.pledge_services import credit_pledge_deed  # noqa: PLC0415

    credit_pledge_deed(grant)

    from world.magic.services.aura import (  # noqa: PLC0415
        fire_aura_threshold_crossings,
        recompute_aura,
    )

    # Two separate steps chained here: recompute the aura, then check whether
    # the drift crossed any authored AuraAffinityThreshold (#1737).
    drift = recompute_aura(character_sheet)
    if drift is not None:
        fire_aura_threshold_crossings(character_sheet, drift)

    # #4733: a deed that grew the character's own affinity while they hold convertible drift
    # opens (or extends) the scene's drift conversion offer. Runs after the aura recompute so
    # the offer reads the aura this grant just produced.
    from world.magic.services.drift import open_or_extend_conversion_offer  # noqa: PLC0415

    open_or_extend_conversion_offer(grant)

    # #5177: a deed that grew a resonance the character is compelled by is giving in to it.
    # It returns at once, with no query, for a row carrying no corruption.
    from world.magic.services.impulses import give_in_to_compulsion  # noqa: PLC0415

    give_in_to_compulsion(grant, cr)

    # Endorsement/resonance-threshold distinction rank-up (#2037 Decision 8) — only
    # for the "sustained endorsements" identity-reinforcing-play sources. Gating on
    # ACCELERATED_GAIN_SOURCES also prevents a feedback loop: the DISTINCTION source
    # itself (a distinction's own resonance seed) is never in that set, so ranking a
    # distinction up here can't immediately re-trigger itself via its own seed grant.
    if source in ACCELERATED_GAIN_SOURCES:
        try:
            from world.magic.services.distinction_resonance import (  # noqa: PLC0415
                check_distinction_rank_thresholds,
            )

            check_distinction_rank_thresholds(character_sheet, resonance)
        except Exception:
            # A failed threshold check forfeits only the rank-up bonus, never the
            # resonance grant it's layered on top of. This runs inside this
            # function's own @transaction.atomic — an uncaught exception here would
            # roll back the whole grant (mirrors the PROJECT_CONTRIBUTION precedent
            # in world/projects/services.py). grant_distinction wraps its own writes
            # in a nested `with transaction.atomic():` block (its own savepoint), so
            # a failure there has already unwound cleanly by the time it propagates
            # to this catch — the grant recorded above stands either way.
            logger.exception(
                "Endorsement-threshold distinction rank-up check failed for "
                "character sheet #%s / resonance #%s — resonance grant stands, "
                "rank-up forfeited.",
                character_sheet.pk,
                resonance.pk,
            )

    return cr


def _resolve_gain_bonus(
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    source: str,
    *,
    act_stat: Trait | None,
    gain_bonus: GainBonus | None,
) -> GainBonus:
    """The bonus check result a gain of ``source`` grows by (#5308).

    An exempt source takes none and refuses one. A caller-rolled source takes the one its
    caller rolled; with none, it pays its plain amount while the bonus check is off (so a
    caller not yet rolling keeps working) and refuses once the check is configured, because
    a gain nobody rolled for would silently skip it. A rolled source takes a passed result
    or rolls one for the resonance's affinity.

    Raises:
        ValueError: A bonus was passed for an exempt source, or a caller-rolled source was
            granted with the bonus check on and no result.
    """
    if source in GAIN_BONUS_EXEMPT_SOURCES:
        if gain_bonus is not None:
            msg = f"{source} source takes no bonus check; gain_bonus= must not be passed."
            raise ValueError(msg)
        return NO_GAIN_BONUS
    if gain_bonus is not None:
        return gain_bonus
    if source in GAIN_BONUS_CALLER_ROLLED_SOURCES:
        from world.magic.services.gain import get_resonance_gain_config  # noqa: PLC0415

        if get_resonance_gain_config().bonus_check_type_id is None:
            return NO_GAIN_BONUS
        msg = f"{source} source requires gain_bonus= kwarg: its caller rolls the bonus check."
        raise ValueError(msg)
    return roll_gain_bonus(character_sheet, resonance.affinity, source=source, stat=act_stat)


@transaction.atomic
def seed_creation_resonance(
    character_sheet: CharacterSheet, resonance: ResonanceModel, lifetime: int
) -> ResonanceGrant:
    """Seed a new character's starting resonance: lifetime only, never spendable (#5123).

    A creation pick is who the character already is, not currency they earned: it adds
    ``lifetime`` to the row's ``lifetime_earned`` and leaves ``balance`` alone, writes a
    ``CHARACTER_CREATION`` ledger row, then recomputes the aura so the starting shares come
    from the weights. Unlike ``grant_resonance`` it fires no thresholds, offers or pledge
    favor, since nothing happened in play.

    Raises:
        InvalidImbueAmount: If ``lifetime`` <= 0.
    """
    if lifetime <= 0:
        msg = "Creation resonance must be positive."
        raise InvalidImbueAmount(msg)
    row, _ = CharacterResonance.objects.get_or_create(
        character_sheet=character_sheet,
        resonance=resonance,
        defaults={"balance": 0, "lifetime_earned": 0},
    )
    row.lifetime_earned += lifetime
    row.save(update_fields=["lifetime_earned"])
    grant = ResonanceGrant.objects.create(
        character_sheet=character_sheet,
        resonance=resonance,
        amount=lifetime,
        source=GainSource.CHARACTER_CREATION,
    )
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415

    recompute_aura(character_sheet)
    return grant


def _validate_grant_source_shape(  # noqa: PLR0913
    source: str,
    *,
    room_profile: RoomProfile | None,
    pose_endorsement: PoseEndorsement | None = None,
    scene_entry_endorsement: SceneEntryEndorsement | None = None,
    outfit_item_facet: ItemFacet | None = None,
    sanctum_details: SanctumDetails | None = None,
    project: Project | None = None,
    entry_flourish: EntryFlourishRecord | None = None,
    dramatic_moment: DramaticMomentTag | None = None,
    style_presentation_endorsement: StylePresentationEndorsement | None = None,
    mission_deed_reward_line: MissionDeedRewardLine | None = None,
    source_character_distinction: CharacterDistinction | None = None,
    worship_rite_performance: WorshipRitePerformance | None = None,
    kindling_situation: KindlingSituation | None = None,
    settling_rite: SettlingRite | None = None,
    reflection: Reflection | None = None,
) -> None:
    """Raise ValueError if the source discriminator doesn't match the supplied kwargs.

    Table-driven: ``_SOURCE_REQUIRED_KWARG`` maps each strict source to the
    (kwarg-value, kwarg-name) pair that must be non-None. ``STAFF_GRANT`` is
    intentionally absent — its ``staff_account`` is nullable by design.
    """
    required = _SOURCE_REQUIRED_KWARG.get(source)
    if required is not None:
        value, name = required(
            room_profile=room_profile,
            pose_endorsement=pose_endorsement,
            scene_entry_endorsement=scene_entry_endorsement,
            outfit_item_facet=outfit_item_facet,
            sanctum_details=sanctum_details,
            project=project,
            entry_flourish=entry_flourish,
            dramatic_moment=dramatic_moment,
            style_presentation_endorsement=style_presentation_endorsement,
            mission_deed_reward_line=mission_deed_reward_line,
            source_character_distinction=source_character_distinction,
            worship_rite_performance=worship_rite_performance,
            kindling_situation=kindling_situation,
            settling_rite=settling_rite,
            reflection=reflection,
        )
        if value is None:
            msg = f"{source} source requires {name}= kwarg."
            raise ValueError(msg)
        return
    if source in (
        GainSource.STAFF_GRANT,
        GainSource.MISSION_REPORT,
        GainSource.STAKE_REWARD,
        GainSource.COMBO_DISCOVERY,
        GainSource.COMPROMISE,
        GainSource.FALL_CONVERSION,
        GainSource.DRIFT_CORRECTION,
        GainSource.SINEATING,
        GainSource.CORRUPTION_CLEANSING,
        GainSource.CHARACTER_CREATION,
        # #5177: settling the Mire; the Sinner's and the Sineater's payouts name no typed row.
        GainSource.MIRE_PURIFIED,
        GainSource.SUCCUMB_BONUS,
        GainSource.SINEATER_FALL,
        # #5181: an Anima ritual's resonance names no typed row either.
        GainSource.ANIMA_RITUAL,
        # #5308: the harvest of waiting trickles names no typed row either.
        GainSource.TRICKLE_HARVEST,
        # #5327: a mark names no typed row; the recorded act holds the link back to the grant.
        GainSource.MARKED_ACT,
    ):
        # No typed source FK — the grant is attributed by discriminator only.
        return
    msg = f"Unknown GainSource: {source!r}"
    raise ValueError(msg)


_SOURCE_REQUIRED_KWARG: dict[str, Callable[..., tuple[object | None, str]]] = {
    GainSource.POSE_ENDORSEMENT: lambda **kw: (kw["pose_endorsement"], "pose_endorsement"),
    GainSource.SCENE_ENTRY: lambda **kw: (kw["scene_entry_endorsement"], "scene_entry_endorsement"),
    GainSource.OUTFIT_TRICKLE: lambda **kw: (kw["outfit_item_facet"], "outfit_item_facet"),
    GainSource.ROOM_RESIDENCE: lambda **kw: (kw["room_profile"], "room_profile"),
    GainSource.SANCTUM_WEAVING: lambda **kw: (kw["sanctum_details"], "sanctum_details"),
    GainSource.SANCTUM_OWNER_BONUS: lambda **kw: (kw["sanctum_details"], "sanctum_details"),
    GainSource.SANCTUM_DISSOLUTION_RECOVERY: lambda **kw: (
        kw["sanctum_details"],
        "sanctum_details",
    ),
    GainSource.PROJECT_CONTRIBUTION: lambda **kw: (kw["project"], "project"),
    GainSource.ENTRY_FLOURISH: lambda **kw: (kw["entry_flourish"], "entry_flourish"),
    GainSource.DRAMATIC_MOMENT: lambda **kw: (kw["dramatic_moment"], "dramatic_moment"),
    GainSource.STYLE_PRESENTATION: lambda **kw: (
        kw["style_presentation_endorsement"],
        "style_presentation_endorsement",
    ),
    GainSource.MISSION_REWARD: lambda **kw: (
        kw["mission_deed_reward_line"],
        "mission_deed_reward_line",
    ),
    GainSource.DISTINCTION: lambda **kw: (
        kw["source_character_distinction"],
        "source_character_distinction",
    ),
    GainSource.WORSHIP_RITE: lambda **kw: (
        kw["worship_rite_performance"],
        "worship_rite_performance",
    ),
    GainSource.KINDLED_DEED: lambda **kw: (kw["kindling_situation"], "kindling_situation"),
    # Both the rite and the reflection are required; naming the rite when either is missing
    # keeps the one-value shape of this table (the constraint refuses a row with only one).
    GainSource.EMBRACED_DEED: lambda **kw: (
        kw["settling_rite"] if kw["reflection"] is not None else None,
        "settling_rite and reflection",
    ),
    # Succumbing to the Mire (#5177) carries the rite and the burden reflection the same way.
    GainSource.SUCCUMBED: lambda **kw: (
        kw["settling_rite"] if kw["reflection"] is not None else None,
        "settling_rite and reflection",
    ),
}


def _crossing_requirements(
    thread: Thread, next_level: int, character_sheet: CharacterSheet
) -> tuple[bool, list[str]]:
    """Check a crossing gate, allowing non-crossing levels (thresholds are stored levels)."""
    if not is_thread_crossing_level(next_level):
        return True, []
    from world.progression.services.spends import (  # noqa: PLC0415
        check_requirements_for_thread_crossing,
    )

    threshold = ThreadCrossingThreshold.objects.filter(
        target_kind=thread.target_kind, level=next_level
    ).first()
    if threshold is None:
        return True, []
    return check_requirements_for_thread_crossing(character_sheet.character, threshold)


def _check_imbue_level_advance(  # noqa: PLR0913
    thread: Thread,
    next_level: int,
    cap: int,
    character_sheet: CharacterSheet,
    *,
    amount: int,
    imbue_multiplier: int,
    resonance: ResonanceModel,
) -> tuple[bool, str, list[str]]:
    """Evaluate whether a thread can advance to ``next_level``.

    Returns ``(should_advance, blocked_by, blocked_requirement_messages)``.
    When ``should_advance`` is ``False``, ``blocked_by`` names the gate that
    stopped advancement (or ``"NONE"`` if the bucket is simply exhausted and
    ``blocked_requirement_messages`` carries crossing-requirement failures.
    """
    cost = dp_cost_for_step(thread.level) * imbue_multiplier
    if thread.developed_points < cost:
        if amount == 0:
            return False, "INSUFFICIENT_BUCKET", []
        return False, "NONE", []
    if next_level % 10 == 0:
        unlocked = ThreadLevelUnlock.objects.filter(
            thread=thread,
            unlocked_level=next_level,
        ).exists()
        if not unlocked:
            return False, "XP_LOCK", []
    met, failed = _crossing_requirements(thread, next_level, character_sheet)
    if not met:
        return False, "CROSSING_REQUIREMENT", failed
    if next_level > cap:
        blocked_by = (
            "LEVEL_CAP"
            if compute_level_cap(character_sheet) <= compute_anchor_cap(thread, resonance)
            else "ANCHOR_CAP"
        )
        return False, blocked_by, []
    return True, "NONE", []


def _charge_imbue_ap(character_sheet: CharacterSheet) -> ActionPointPool:
    """Compute and charge the flat AP cost for a Rite of Imbuing (#2467).

    The Unbound magic-learning AP surcharge (#2442) applies automatically via
    the same ``magic_learning_ap_cost`` modifier resolution technique learning
    uses. Raises ``MagicError`` if the character cannot afford the cost.

    Args:
        character_sheet: The character performing the imbuing.

    Returns:
        The character's ActionPointPool (already charged).

    Raises:
        MagicError: If the character has insufficient AP.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.services.gift_acquisition import (  # noqa: PLC0415
        get_gift_acquisition_config,
        magic_learning_ap_cost_surcharge_percent,
    )

    config = get_gift_acquisition_config()
    base_ap = config.imbue_ap_cost
    surcharge_percent = magic_learning_ap_cost_surcharge_percent(character_sheet)
    ap_cost = math.ceil(base_ap * (100 + surcharge_percent) / 100)

    ap_pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if not ap_pool.can_afford(ap_cost):
        msg = f"Insufficient action points (need {ap_cost}, have {ap_pool.current})."
        raise MagicError(msg)
    if not ap_pool.spend(ap_cost):
        msg = f"Insufficient action points (need {ap_cost}, have {ap_pool.current})."
        raise MagicError(msg)
    return ap_pool


def _check_imbue_request(character_sheet: CharacterSheet, thread: Thread, amount: int) -> None:
    """Refuse an imbue the thread cannot take: a bad amount or a stranger's thread. Any
    resonance may feed any thread, a Gift's included (#5123)."""
    if amount < 0:
        msg = "Imbue amount must be non-negative."
        raise InvalidImbueAmount(msg)
    if thread.owner_id != character_sheet.pk:
        msg = "Character does not own thread."
        raise InvalidImbueAmount(msg)


@transaction.atomic
def spend_resonance_for_imbuing(
    character_sheet: CharacterSheet,
    thread: Thread,
    resonance: ResonanceModel,
    amount: int,
    **_ritual_dispatch_kwargs: object,  # ritual dispatch also forwards ``ritual=``
) -> ThreadImbueResult:
    """Deduct ``resonance`` balance, add it to the thread's row, and advance the thread level.

    Spec A §3.2, #5123. The thread keeps how much of each resonance went into it on its
    ``ThreadResonance`` rows (created on first use of a resonance), each a cumulative
    total: levelling spends ``developed_points`` and never lowers a row. The leading
    resonance is refreshed afterwards, so a resonance whose total overtakes the others
    becomes ``thread.resonance``. A level costs ``dp_cost_for_step(current_level)``, the
    shared development cost curve, times the thread kind's imbue cost multiplier.
    Advancement continues until the bucket is exhausted, the next level hits an XP-lock gate,
    or the effective cap is reached.

    Args:
        character_sheet: Character performing the imbuing.
        thread: Thread to advance (must be owned by character_sheet).
        resonance: The resonance whose balance pays. Anchor caps keyed on a
            resonance (facet, organization) key on this one.
        amount: Resonance balance to spend (0 = drain existing bucket only).

    Returns:
        ThreadImbueResult dataclass.

    Raises:
        InvalidImbueAmount: If amount < 0 or thread.owner != character_sheet.
        AnchorCapExceeded: If thread is already at effective cap (``LevelCapExceeded``,
            a subclass, when the character-level cap is the one binding it).
        ResonanceInsufficient: If the character holds too little of ``resonance``.
    """
    from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415
    from world.magic.services.thread_rows import (  # noqa: PLC0415
        add_to_resonance_row,
        refresh_leading_resonance,
    )

    if character_sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    _check_imbue_request(character_sheet, thread, amount)
    cap = compute_effective_cap(thread, resonance)
    if thread.level >= cap:
        msg = "Thread already at effective cap."
        raise cap_exceeded_error(thread, resonance)(msg)

    cr = CharacterResonance.objects.filter(
        character_sheet=character_sheet,
        resonance=resonance,
    ).first()
    if amount and (cr is None or cr.balance < amount):
        msg = "Need " + str(amount) + ", have " + str(cr.balance if cr else 0) + "."
        raise ResonanceInsufficient(msg)

    # AP charge (development time) — flat per rite, Unbound surcharge applies.
    _charge_imbue_ap(character_sheet)

    starting_level = thread.level
    if amount:
        cr.balance -= amount
        thread.developed_points += amount
        add_to_resonance_row(thread, resonance, amount)

    blocked_by: str = "NONE"
    blocked_requirement_messages: list[str] = []
    imbue_multiplier = get_imbue_cost_multiplier(thread.target_kind)
    while True:
        next_level = thread.level + 1
        should_advance, blocked_by, blocked_requirement_messages = _check_imbue_level_advance(
            thread,
            next_level,
            cap,
            character_sheet,
            amount=amount,
            imbue_multiplier=imbue_multiplier,
            resonance=resonance,
        )
        if not should_advance:
            break
        cost = dp_cost_for_step(thread.level) * imbue_multiplier
        thread.level = next_level
        thread.developed_points -= cost

    if cr is not None:
        cr.save(update_fields=["balance"])
    thread.save(update_fields=["level", "developed_points"])
    refresh_leading_resonance(thread)
    character_sheet.character.threads.invalidate()

    recompute_max_health_with_threads(character_sheet)
    _apply_mantle_level_conditions(thread, character_sheet, starting_level)

    from world.magic.crossing.ceremony import execute_crossing_ceremonies  # noqa: PLC0415

    execute_crossing_ceremonies(
        thread=thread, starting_level=starting_level, new_level=thread.level
    )

    return ThreadImbueResult(
        resonance_spent=amount,
        developed_points_added=amount,
        levels_gained=thread.level - starting_level,
        new_level=thread.level,
        new_developed_points=thread.developed_points,
        blocked_by=blocked_by,  # type: ignore[arg-type]
        blocked_requirement_messages=blocked_requirement_messages,
    )


def _apply_mantle_level_conditions(
    thread: Thread, character_sheet: CharacterSheet, starting_level: int
) -> None:
    """A MANTLE thread's level rose: give the wearer the worn conditions its new mantle
    levels unlock, with the mantle still on (#5074).

    Applies only the item's rows whose mantle level lies above the level the thread held
    and at most the level it holds now, so a level raise never brings back a condition that
    was dispelled at a lower level. Recording a clearance does not change the level, so it
    needs no hook.
    """
    if thread.target_kind != TargetKind.MANTLE or thread.level <= starting_level:
        return
    from world.items.models import ItemWornCondition  # noqa: PLC0415
    from world.items.services.worn_conditions import reconcile_worn_conditions  # noqa: PLC0415

    rows = ItemWornCondition.objects.filter(
        item_instance_id=thread.target_mantle.item_instance_id,
        mantle_level__gt=thread_rung(starting_level),
        mantle_level__lte=thread_rung(thread.level),
    )
    reconcile_worn_conditions(character_sheet, apply_rows=rows)


# =============================================================================
# Phase 12 — spend_resonance_for_pull (Spec A §5.4 + §7.4)
# =============================================================================


# Always-in-action target kinds: relationship anchors are the player's assertion
# of involvement; the system never validates them per Spec §5.4 line 1450.
# FACET threads are gated by the worn-items check (NoMatchingWornFacetItemsError),
# not by anchor-involvement — so they bypass the generic in-action check here.
# COVENANT_ROLE threads gate explicitly on engagement (see _anchor_in_action below
# for the COVENANT_ROLE arm). Slice A §3.6.
_ALWAYS_IN_ACTION_KINDS = frozenset(
    {
        TargetKind.RELATIONSHIP_TRACK,
        TargetKind.RELATIONSHIP_CAPSTONE,
        TargetKind.FACET,
        # A species GIFT thread is intrinsic to the character — always available to
        # pull (no anchor target in the action graph to validate against) (#1580).
        TargetKind.GIFT,
        # An ORGANIZATION thread is intrinsic — org membership is always in-action.
        TargetKind.ORGANIZATION,
    }
)


def _anchor_in_action(thread: Thread, ctx: PullActionContext) -> bool:
    """Return True iff ``thread``'s anchor is involved in the action (Spec A §5.2).

    Relationship anchors are always considered in-action (player asserts
    involvement). Other kinds are matched against the explicit ``involved_*``
    tuples on the context — the caller is responsible for populating those.

    COVENANT_ROLE threads gate on engagement: the character must currently be
    fulfilling the role for one of their covenants (Slice A §3.6).

    ``ctx.excluded_kinds`` (#1919): checked BEFORE the ``_ALWAYS_IN_ACTION_KINDS``
    shortcut so a GIFT thread — always in-action for casts where the technique
    IS the gift anchor — is rejected for social-action pulls where no gift
    technique is involved. Social pulls pass ``frozenset({TargetKind.GIFT})``.
    """
    if ctx.excluded_kinds and thread.target_kind in ctx.excluded_kinds:
        return False
    if thread.target_kind in _ALWAYS_IN_ACTION_KINDS:
        return True
    if thread.target_kind == TargetKind.TRAIT:
        return thread.target_trait_id in ctx.involved_traits
    if thread.target_kind == TargetKind.TECHNIQUE:
        # #4097: carries through prerequisites - a thread on A also empowers
        # B when B requires A (transitively), at the thread's full level.
        # Cast power and paid pulls both resolve through this predicate, so
        # both get the carry; the ambient capability sweep below
        # (``_anchor_ambiently_active``) is deliberately left on the bare
        # ``involved_techniques`` tuple - this task only widens in-action.
        return thread.target_technique_id in ctx.involved_technique_closure
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        sheet = thread.owner
        engaged_roles = sheet.character.covenant_roles.currently_engaged_roles()
        target_pk = thread.target_covenant_role_id
        return any(role.pk == target_pk for role in engaged_roles)
    if thread.target_kind == TargetKind.SANCTUM:
        room_obj_id = thread.target_sanctum_details.feature_instance.room_profile.objectdb_id
        return room_obj_id in ctx.involved_objects
    return False


def _anchor_ambiently_active(
    thread: Thread,
    ctx: PullActionContext,
    *,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — presence/equipment checks need the game object
    gift_id_by_technique: Mapping[int, int] | None = None,
) -> bool:
    """Return True iff ``thread`` is DEMONSTRABLY active right now (#2708).

    The passive sibling of :func:`_anchor_in_action`. The two differ on purpose:
    ``_anchor_in_action`` lets a player *assert* involvement for kinds with no anchor in
    the action graph (GIFT, RELATIONSHIP_*), which is fair because the pull is paid for.
    A passive capability contribution costs nothing, so assertion is not enough — every
    arm here tests real state. Concretely: a pyromancer's fire-gift thread must not raise
    their ability to climb a wall.

    ORGANIZATION deliberately returns False. Its rule ("tied to organization missions or
    activities", ratified 2026-07-25) needs a marker ``PullActionContext`` does not carry;
    shipping an arm that can never fire would be worse than omitting it. Tracked as a
    needs-design question #2731.

    ``gift_id_by_technique`` lets a batch caller (``build_applicable_threads``, which
    invokes this once per thread in a loop, or a caller sweeping many technique-contexts
    for one character) resolve a technique_id -> gift_id mapping ONCE — covering as many
    techniques as the caller likes, even a whole sweep's worth spanning several
    techniques/gifts — and pass it through, instead of this function re-querying
    ``Technique`` for every GIFT thread. :func:`_gift_in_action` always narrows the
    mapping down to THIS call's own ``ctx.involved_techniques`` before deciding, so a
    wider mapping can never leak a thread active-on-one-technique's gift into a
    different technique's evaluation (#2708 review — passing a pre-flattened gift-id
    *set* instead of this mapping was the unsound shape that made that leak possible). A
    lone call (e.g. from tests) omits the kwarg and :func:`_gift_in_action` computes the
    mapping internally — single-call correctness is preserved.

    ``ctx.excluded_kinds`` (#1919) is honoured ONLY via the COVENANT_ROLE arm, which
    delegates straight to :func:`_anchor_in_action` (the function that actually checks
    it). Every other arm below ignores it entirely — harmless today because no caller of
    this function currently populates ``excluded_kinds`` on a context it also threads
    through here, but the next arm author (or the first caller to do so) should not
    assume exclusion is honoured uniformly across kinds without checking each arm.
    """
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        # Identical to the pull predicate: engagement is already demonstrable.
        return _anchor_in_action(thread, ctx)
    if thread.target_kind == TargetKind.TECHNIQUE:
        return thread.target_technique_id in ctx.involved_techniques
    if thread.target_kind == TargetKind.GIFT:
        return _gift_in_action(thread, ctx, gift_id_by_technique=gift_id_by_technique)
    if thread.target_kind == TargetKind.TRAIT:
        return thread.target_trait_id in ctx.involved_traits
    if thread.target_kind == TargetKind.SANCTUM:
        room_obj_id = thread.target_sanctum_details.feature_instance.room_profile.objectdb_id
        location = character.location
        return location is not None and location.pk == room_obj_id
    if thread.target_kind == TargetKind.RELATIONSHIP_TRACK:
        return _relationship_target_present(thread.target_relationship, character)
    if thread.target_kind == TargetKind.RELATIONSHIP_CAPSTONE:
        return _relationship_target_present(thread.target_capstone, character)
    if thread.target_kind == TargetKind.FACET:
        # Direct handler access (no ``sheet_data`` hop needed) — the equipment
        # handler hangs off the Character typeclass itself (#2708 verification;
        # mirrors the worn-facet gate in ``_validate_pull_threads_for_commit``).
        return bool(character.equipped_items.item_facets_for(thread.target_facet))
    if thread.target_kind == TargetKind.MANTLE:
        return _mantle_worn(thread.target_mantle, character)
    return False


def _gift_in_action(
    thread: Thread,
    ctx: PullActionContext,
    *,
    gift_id_by_technique: Mapping[int, int] | None = None,
) -> bool:
    """True iff any technique the action involves belongs to this thread's gift.

    ``gift_id_by_technique``, when supplied, is a technique_id -> gift_id mapping that
    MAY cover more techniques than just ``ctx.involved_techniques`` (a batch caller may
    pass one mapping covering an entire multi-technique sweep). This function ALWAYS
    narrows the mapping down to ``ctx.involved_techniques`` before testing membership —
    that narrowing is the whole point: it's what makes it safe to hand this call a
    mapping built for a wider sweep without the extra entries changing the answer.
    Never trust a pre-flattened gift-id set here — that shape can't be narrowed per call
    and silently leaks an unrelated technique's gift into this thread's evaluation
    (#2708 review Critical finding). When omitted (a standalone call), the mapping is
    computed here so single-call correctness is preserved.
    """
    if not ctx.involved_techniques:
        return False
    if gift_id_by_technique is None:
        gift_id_by_technique = resolve_gift_ids_by_technique(ctx.involved_techniques)
    involved_gift_ids = {
        gift_id_by_technique[tid] for tid in ctx.involved_techniques if tid in gift_id_by_technique
    }
    return thread.target_gift_id in involved_gift_ids


def resolve_gift_ids_by_technique(involved_techniques: tuple[int, ...]) -> dict[int, int]:
    """Resolve technique_id -> gift_id for ``involved_techniques`` in a single query.

    Batch callers precompute this ONCE — optionally over the union of every technique in
    a whole multi-call sweep, not just one call's ``ctx.involved_techniques`` — and thread
    it through ``_anchor_ambiently_active``'s ``gift_id_by_technique`` kwarg, rather than
    letting ``_gift_in_action`` re-query per GIFT thread in the predicate loop (#2708
    review — a character with several owned Gifts fired one ``Technique`` query per GIFT
    thread on every ambient evaluation).

    Deliberately returns a technique_id -> gift_id MAPPING, not a flattened set of gift
    ids: ``_gift_in_action`` narrows this mapping down to each call's own
    ``ctx.involved_techniques`` before testing membership, so passing a mapping that
    covers more techniques than one particular call needs is always safe. A pre-flattened
    set has no way to be narrowed back down per call and was the unsound shape (#2708
    review Critical finding) that let one technique's gift leak into a different
    technique's ambient evaluation.
    """
    if not involved_techniques:
        return {}
    from world.magic.models import Technique  # noqa: PLC0415

    return dict(Technique.objects.filter(pk__in=involved_techniques).values_list("pk", "gift_id"))


def _relationship_target_present(
    owner_row: CharacterRelationship | RelationshipCapstone | None,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — room-contents check needs the game object
) -> bool:
    """True iff the other party to this relationship is in the acting character's room.

    ``owner_row`` is a CharacterRelationship (the weaver's own side, RELATIONSHIP_TRACK,
    #3957) or a RelationshipCapstone (RELATIONSHIP_CAPSTONE, exposes ``.relationship``);
    both resolve to a CharacterSheet ``target``. CharacterSheet shares ObjectDB's pk, so
    the presence check is a pk comparison — no extra fetch.
    """
    location = character.location
    if owner_row is None or location is None:
        return False
    side = relationship_side_from_row(owner_row)
    target_pk = side.target_id
    return any(obj.pk == target_pk for obj in location.contents)


def _mantle_worn(
    mantle: Mantle | None,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — equipment check needs the game object
) -> bool:
    """True iff the ItemInstance that IS this mantle (items/models.py:1693) is equipped."""
    if mantle is None:
        return False
    return any(
        equipped.item_instance_id == mantle.item_instance_id
        for equipped in character.equipped_items
    )


def _derive_pull_power(
    character_sheet: CharacterSheet | None,
) -> tuple[CapabilityPowerConfig | None, int]:
    """Fetch the capability power config and context_free_power for a pull (#2730).

    Returns ``(None, 0)`` when ``character_sheet`` is None (the power_terms
    caller has no sheet — CAPABILITY_GRANT curving is a no-op there). When a
    config row exists, derives ``context_free_power`` from the character's
    thread handler (same figure the passive path uses, ADR-0169 D6).
    """
    if character_sheet is None:
        return None, 0
    from world.magic.services.capability_curve import (  # noqa: PLC0415
        get_capability_power_config,
    )

    power_config = get_capability_power_config()
    if power_config is None:
        return None, 0
    try:
        context_free_power = character_sheet.character.threads.context_free_power
    except AttributeError:
        from world.magic.handlers import CharacterThreadHandler  # noqa: PLC0415

        handler = CharacterThreadHandler(character_sheet.character)
        context_free_power = handler.context_free_power
    return power_config, context_free_power


def _compute_capability_grant_value(
    row: ThreadPullEffect,
    *,
    inactive: bool,
    multiplier: Decimal,
    power_config: CapabilityPowerConfig | None,
    context_free_power: int,
) -> int | None:
    """Compute the frozen curved magnitude for a CAPABILITY_GRANT row (#2730).

    Returns ``None`` for non-CAPABILITY_GRANT kinds. For inactive (non-combat)
    rows, returns 0 (cost still paid). For active rows with a config, curves
    via ``apply_capability_curve``. Without a config, returns the authored
    base unchanged (inert invariant, ADR-0169 D2).
    """
    if row.effect_kind != EffectKind.CAPABILITY_GRANT:
        return None
    if inactive:
        return 0
    if power_config is None:
        return row.capability_grant_value
    from world.magic.services.capability_curve import apply_capability_curve  # noqa: PLC0415

    return apply_capability_curve(
        row.capability_grant_value,
        power=context_free_power,
        sensitivity=multiplier,
        config=power_config,
    )


# ASSUME_ALTERNATE_SELF, CAPABILITY_GRANT, NARRATIVE_ONLY and CORRUPTION_RESISTANCE
# have no numeric payload; their scaled_value must be None. ASSUME_ALTERNATE_SELF
# derives its runtime stat-suite from the target form's selected combat profile
# (crit/mid/fail bands). CORRUPTION_RESISTANCE derives its runtime value from
# CharacterResonance.lifetime_helped (Spec B §10.2) — it is applied directly in
# accrue_corruption, not via a scaled_value here.
_NO_NUMERIC_PAYLOAD = frozenset(
    {
        EffectKind.ASSUME_ALTERNATE_SELF,
        EffectKind.CAPABILITY_GRANT,
        EffectKind.NARRATIVE_ONLY,
        EffectKind.CORRUPTION_RESISTANCE,
    }
)

# VITAL_BONUS and RESISTANCE are combat-only consumers: their snapshot lives on
# CombatPullResolvedEffect and is read on the combat path, so ephemeral (RP) pulls
# flag them inactive (cost still paid). CAPABILITY_GRANT is active in non-combat
# context — the frozen value is persisted via the Thread Surge condition +
# EphemeralPullCapabilityGrant sidecar (#2840).
_COMBAT_ONLY_KINDS = frozenset({EffectKind.VITAL_BONUS, EffectKind.RESISTANCE})


def _worn_facet_aggregate(thread: Thread) -> Decimal | None:
    """Summed quality multiplier of worn items bearing this thread's facet.

    None when the wearer has no matching items, which means the effect row does not
    resolve at all. Other threads in the sweep are unaffected.
    """
    matching = thread.owner.character.equipped_items.item_facets_for(thread.target_facet)
    if not matching:
        return None
    # Decimal(str(...)) coerces in case a multiplier surfaces as float (e.g. via
    # factory or .values() in test fixtures); DecimalField normally returns Decimal
    # but this is belt-and-suspenders.
    return sum(
        (
            (
                Decimal(str(item_facet.item_instance.quality_tier.stat_multiplier))
                if item_facet.item_instance.quality_tier is not None
                else Decimal(1)
            )
            * Decimal(str(item_facet.attachment_quality_tier.stat_multiplier))
            for item_facet in matching
        ),
        Decimal(0),
    )


def _resolve_one_pull_effect(  # noqa: PLR0913 - mirrors resolve_pull_effects' inputs
    thread: Thread,
    row: ThreadPullEffect,
    *,
    effect_tier: int,
    multiplier: Decimal,
    target: ObjectDB | None,
    in_combat: bool,
    power_config: object,
    context_free_power: int,
) -> ResolvedPullEffect | None:
    """One (thread x tier x row) triple, or None when the row does not apply."""
    from world.magic.services.pull_modulation import apply_target_modulation  # noqa: PLC0415

    authored = (
        row.flat_bonus_amount
        or row.intensity_bump_amount
        or row.vital_bonus_amount
        or row.resistance_amount
    )
    has_numeric_payload = row.effect_kind not in _NO_NUMERIC_PAYLOAD

    # round(), not int() truncation: thread_level_multiplier (#1718) returns a
    # fractional Decimal for levels 1-9, and rounding to the nearest int is fairer
    # to the player than always flooring.
    if thread.target_kind == TargetKind.FACET:
        worn_aggregate = _worn_facet_aggregate(thread)
        if worn_aggregate is None:
            return None
        base_scaled = (
            round((authored or 0) * multiplier * worn_aggregate) if has_numeric_payload else None
        )
    else:
        base_scaled = round((authored or 0) * multiplier) if has_numeric_payload else None

    if has_numeric_payload:
        base_scaled = apply_target_modulation(thread, target, row, base_scaled)

    inactive = row.effect_kind in _COMBAT_ONLY_KINDS and not in_combat
    # #2730: the frozen curved magnitude for CAPABILITY_GRANT, using the same
    # apply_capability_curve formula as the passive path
    # (handlers.py:_passive_capability_grants_cache), with context_free_power as the
    # power figure (ADR-0169 D6).
    capability_grant_value = _compute_capability_grant_value(
        row,
        inactive=inactive,
        multiplier=multiplier,
        power_config=power_config,
        context_free_power=context_free_power,
    )
    return ResolvedPullEffect(
        kind=row.effect_kind,
        authored_value=authored,
        # ResolvedPullEffect.level_multiplier is int-typed (persisted to
        # CombatPullResolvedEffect.level_multiplier, a PositiveSmallIntegerField);
        # round() the transient Decimal multiplier to an int for the snapshot (#1718).
        level_multiplier=round(multiplier),
        level_multiplier_exact=multiplier,
        scaled_value=0 if inactive else base_scaled,
        vital_target=row.vital_target,
        source_thread=thread,
        source_thread_level=thread.level,
        source_tier=effect_tier,
        granted_capability=row.capability_grant,
        narrative_snippet=row.narrative_snippet,
        inactive=inactive,
        inactive_reason=("requires combat context" if inactive else None),
        target_form=row.target_form,
        resistance_damage_type=row.resistance_damage_type,
        capability_grant_value=capability_grant_value,
    )


def _beseeched_level(
    thread: Thread, level_read: int, beseech_bonus_thread_id: int | None, beseech_bonus: int
) -> int:
    """Return ``level_read``, plus the beseech bonus for the beseeched thread (#1718)."""
    if beseech_bonus_thread_id is not None and thread.pk == beseech_bonus_thread_id:
        return level_read + beseech_bonus
    return level_read


def kindled_boost_levels(
    resonance: ResonanceModel, kindled: Mapping[int, KindledStrengthTier] | None
) -> int:
    """The thread levels ``resonance``'s kindled strength adds on a pull, 0 when not kindled.

    The strength's ``pull_levels`` scaled by the resonance's affinity's
    ``kindled_boost_percent`` and rounded down (#5231), so an Abyssal strength can add more
    than a Primal one of the same row.
    """
    tier = kindled.get(resonance.pk) if kindled else None
    if tier is None:
        return 0
    return scale_by_kindled_boost(resonance, tier.pull_levels)


def _second_resonance_boost(
    payer: ResonanceModel, kindled: Mapping[int, KindledStrengthTier] | None, thread: Thread
) -> int:
    """The largest boost a second kindled resonance on ``thread`` adds to ``payer``'s read.

    A second resonance qualifies when the thread holds a row for it, it is kindled, and it is
    Primal where the payer is not, or the reverse. It adds its own boost scaled by its share of
    everything imbued into the thread (Decision 23: the largest addition counts, so two
    qualifying resonances never stack). Nothing counts while nothing is imbued.
    """
    if not kindled:
        return 0
    rows = thread.owner.character.threads.rows_of(thread)
    total = sum(amount for _resonance, amount in rows)
    if total == 0:
        return 0
    payer_is_primal = payer.affinity.name == AFFINITY_PRIMAL
    best = 0
    for resonance, amount in rows:
        if resonance.pk == payer.pk or resonance.pk not in kindled:
            continue
        if (resonance.affinity.name == AFFINITY_PRIMAL) == payer_is_primal:
            continue
        best = max(best, kindled_boost_levels(resonance, kindled) * amount // total)
    return best


def _kindled_level(
    level: int,
    payer: ResonanceModel,
    kindled: Mapping[int, KindledStrengthTier] | None,
    thread: Thread,
) -> int:
    """Return ``level``, plus what the payer's kindling and a second resonance's add (#5231).

    The payer adds its own boost (``kindled_boost_levels``), and the largest boost of a second
    kindled resonance of the other kind on the thread adds on top, scaled by its share of what
    was imbued (``_second_resonance_boost``); the second applies whether or not the payer is
    kindled. Boosts are in thread levels as a player reads them, so ten are one step of
    ``thread_level_multiplier``. That curve dips below level 10, so a sum that would read lower
    than ``level`` is not applied: a kindled payer never reads lower than an unkindled one
    (the guard ``payer_level_read`` has).
    """
    boosted = (
        level
        + kindled_boost_levels(payer, kindled)
        + _second_resonance_boost(payer, kindled, thread)
    )
    return boosted if thread_level_multiplier(boosted) >= thread_level_multiplier(level) else level


def pull_kindled_tiers(
    character_sheet: CharacterSheet, participant: CombatParticipant | None = None
) -> dict[int, KindledStrengthTier]:
    """Resonance id -> its kindled strength tier, read in the surroundings a pull pays in (#5124).

    A pull inside a round reads the round it is declared in; any other pull (a preview, a
    scene cast) reads the character's live fight and mission, the same surroundings her
    resonances panel reads. One read per pull, never per thread.
    """
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.magic.services.kindling import (  # noqa: PLC0415
        active_mission_for,
        kindled_tiers,
        kindling_context_for,
    )

    if participant is not None:
        return kindled_tiers(
            character_sheet,
            resolution=CombatRoundContext(participant),
            mission=active_mission_for(character_sheet),
        )
    context = kindling_context_for(character_sheet)
    return kindled_tiers(character_sheet, resolution=context.resolution, mission=context.mission)


def resolve_pull_effects(  # noqa: PLR0913  — thread × effect_tier resolver; both target (#1831) and beseech (#1718) params are required
    threads: list[Thread],
    tier: int,
    *,
    in_combat: bool,
    target: ObjectDB | None = None,
    beseech_bonus_thread_id: int | None = None,
    beseech_bonus: int = 0,
    character_sheet: CharacterSheet | None = None,
    payers: Mapping[int, ResonanceModel] | None = None,
    kindled: Mapping[int, KindledStrengthTier] | None = None,
) -> list[ResolvedPullEffect]:
    """Resolve every (thread × effect_tier 0..tier) pair into ResolvedPullEffect rows.

    Implements Spec A §5.4 step 3. VITAL_BONUS and RESISTANCE rows in non-combat
    (ephemeral) context are flagged ``inactive`` with ``scaled_value=0`` per spec
    §7.4 lines 1981–1989; the caller still pays full cost. CAPABILITY_GRANT is
    active in non-combat context (#2840) — its frozen curved value is persisted
    via the Thread Surge condition + EphemeralPullCapabilityGrant sidecar.

    ``target`` is the live target this pull's action is directed at (#1831);
    ``None`` for ephemeral / untargeted pulls. Fed through ``apply_target_modulation``
    for numeric-payload rows — a no-op unless a per-``target_kind`` rule exists
    (currently only COVENANT_ROLE / Court-role pulls).

    ``beseech_bonus_thread_id``/``beseech_bonus`` (#1718): when set, the named
    thread's level is treated as ``(thread.level + beseech_bonus)`` for THIS
    resolution's multiplier only — ``ResolvedPullEffect.source_thread_level``
    still reports the thread's REAL level (the bonus is a resolution-time
    override, never a persisted fact).

    ``payers`` (#5123) maps a thread id to the resonance paying for it (the thread's
    leading resonance when absent). Perks are the payer's: its rows, read at
    ``payer_level_read``'s level (which feeds the ``min_thread_level`` gate and the
    multiplier), tier 0 only when the payer is the leading resonance, and nothing at all
    for a payer the thread holds no row for.

    ``kindled`` (#5124) maps a resonance id to its kindled strength tier. A payer in it
    reads the thread ``tier.pull_levels`` higher, beside the beseech boost: for this
    resolution's multiplier only (so INTENSITY_BUMP and every scaled perk grow with it),
    never written to the thread, never moving the ``min_thread_level`` gate or
    ``source_thread_level``. A payer not in the map reads exactly as before.
    """

    # #2730: CAPABILITY_GRANT rows are curved at resolve time using the same
    # apply_capability_curve formula the passive path uses. The power figure
    # is context_free_power (ADR-0169 D6 — capability standing must not
    # flicker based on whether combat is running). Fetched once per sweep.
    # #2730: CAPABILITY_GRANT rows are curved at resolve time using the same
    # apply_capability_curve formula the passive path uses. The power figure is
    # context_free_power (ADR-0169 D6 — capability standing must not flicker based
    # on whether combat is running). Fetched once per sweep.
    power_config, context_free_power = _derive_pull_power(character_sheet)

    resolved: list[ResolvedPullEffect] = []
    for t in threads:
        payer = pull_payer(t, payers)
        level_read = payer_level_read(t, payer)
        if level_read is None:
            continue
        multiplier = thread_level_multiplier(
            _kindled_level(
                _beseeched_level(t, level_read, beseech_bonus_thread_id, beseech_bonus),
                payer,
                kindled,
                t,
            )
        )
        first_tier = 0 if payer.pk == t.resonance_id else 1
        for effect_tier in range(first_tier, tier + 1):
            rows = get_pull_effects_for_thread(
                t, payer, tier=effect_tier, min_thread_level__lte=level_read
            )
            for row in rows:
                effect = _resolve_one_pull_effect(
                    t,
                    row,
                    effect_tier=effect_tier,
                    multiplier=multiplier,
                    target=target,
                    in_combat=in_combat,
                    power_config=power_config,
                    context_free_power=context_free_power,
                )
                if effect is not None:
                    resolved.append(effect)
    return resolved


def _pull_worth_by_affinity(
    character_sheet: CharacterSheet,
    threads: list[Thread],
    action_context: PullActionContext,
    payers: Mapping[int, ResonanceModel] | None,
    worth_by_affinity: Mapping[int, int] | None,
) -> dict[int, int]:
    """The worth in percent of each affinity paying for this pull (#5308).

    One check per distinct paying affinity, rolled with the stat of the action's own roll
    (``action_context.check_type``). An affinity the caller already rolled for, such as a
    cast that also scales its kindled power by the same check, is taken from
    ``worth_by_affinity`` and never rolled again.
    """
    worth = dict(worth_by_affinity or {})
    stat = None
    stat_read = False
    for thread in threads:
        affinity = pull_payer(thread, payers).affinity
        if affinity.pk in worth:
            continue
        if not stat_read:
            check_type = action_context.check_type
            stat = act_stat(check_type) if check_type is not None else None
            stat_read = True
        worth[affinity.pk] = roll_spend_worth(character_sheet, affinity, stat=stat)
    return worth


def _scaled_by_worth(
    resolved: list[ResolvedPullEffect],
    payers: Mapping[int, ResonanceModel] | None,
    worth: Mapping[int, int],
) -> list[ResolvedPullEffect]:
    """``resolved`` with each effect's magnitude scaled by its payer affinity's worth (#5308).

    The thread's scaled value and, for a capability grant, its frozen curved value are both
    multiplied; an inactive row stays 0 and an effect worth 100 percent is returned as is.
    """
    scaled: list[ResolvedPullEffect] = []
    for effect in resolved:
        percent = worth[pull_payer(effect.source_thread, payers).affinity.pk]
        if percent == FULL_WORTH_PERCENT:
            scaled.append(effect)
            continue
        scaled.append(
            dataclasses.replace(
                effect,
                scaled_value=_worth_of(effect.scaled_value, percent),
                capability_grant_value=_worth_of(effect.capability_grant_value, percent),
            )
        )
    return scaled


def _worth_of(value: int | None, percent: int) -> int | None:
    """``value`` at ``percent`` of its worth, None staying None."""
    return None if value is None else value * percent // FULL_WORTH_PERCENT


def _fold_distinction_pull_bonus(
    resolved: list[ResolvedPullEffect],
    *,
    character_sheet: CharacterSheet,
    threads: list[Thread],
    payers: Mapping[int, ResonanceModel] | None = None,
) -> list[ResolvedPullEffect]:
    """Append a synthetic FLAT_BONUS for a distinction's POWER modifier on the paying resonances.

    A distinction expresses potency for a resonance by authoring a ``DistinctionEffect`` on
    a POWER-category ``ModifierTarget`` gated by ``target_resonance`` — the same modifier a
    technique cast already reads via ``_derive_power``'s FLAT stage
    (``magic/services/techniques.py``) (#1834 Task 7). A pull may mix resonances (#5066,
    maintainer ruling 2026-11-11): each distinct paying resonance's scoped potency applies
    once (#5123: the payer, not the thread's leading resonance), and an unscoped POWER
    target (no ``target_resonance``) once for the whole pull, so the bonus is folded once
    per pull, not per thread or tier. No-op (returns ``resolved`` unchanged) when there is
    no matching modifier.

    Not full parity with a cast: ``_derive_power``'s FLAT stage also sums condition-sourced
    POWER contributions (``get_condition_modifier_breakdown``), which this fold does not
    include — only the distinction-authored ``CharacterModifier`` side.
    """
    from world.mechanics.services import power_flat_bonus_for_resonance  # noqa: PLC0415

    resonance_ids = list(dict.fromkeys(pull_payer(thread, payers).pk for thread in threads))
    bonus = power_flat_bonus_for_resonance(character_sheet, None) + sum(
        power_flat_bonus_for_resonance(character_sheet, rid, scoped_only=True)
        for rid in resonance_ids
    )
    if not bonus:
        return resolved
    return [
        *resolved,
        ResolvedPullEffect(
            kind=EffectKind.FLAT_BONUS,
            authored_value=None,
            level_multiplier=1,
            scaled_value=bonus,
            vital_target=None,
            # threads[0] is an arbitrary pick (the bonus belongs to the pull as a whole, so
            # there's no real per-thread attribution for this synthetic entry) — but it IS
            # serialized as source_thread_id over the wire
            # (ResolvedPullEffectSerializer.get_source_thread_id, the pull-preview API).
            # Any future consumer of that field on this row must not treat it as real
            # attribution.
            source_thread=threads[0],
            source_thread_level=threads[0].level,
            source_tier=0,
            granted_capability=None,
            narrative_snippet="",
            target_form=None,
            resistance_damage_type=None,
        ),
    ]


def _validate_pull_threads(
    threads: list[Thread],
    character_sheet: CharacterSheet,
    excluded_kinds: frozenset[str] | None,
) -> None:
    """Validate ownership and excluded-kinds for pull threads (any mix of resonances).

    Raises ``InvalidImbueAmount`` on the first failing thread.
    """
    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if excluded_kinds and t.target_kind in excluded_kinds:
            msg = "Thread anchor is not involved in this action."
            raise InvalidImbueAmount(msg)


def _check_anima_waiver(scene_id: int | None, anima_cost: int) -> int:
    """Return the (possibly zeroed) anima cost after scene waiver checks (#1919).

    When ``scene_id`` is provided and ``anima_cost`` is positive, checks
    whether the scene is high-stakes (active combat or DANGER round). If not,
    the anima cost is waived (zeroed).
    """
    if scene_id is None or anima_cost <= 0:
        return anima_cost

    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.scenes.constants import (  # noqa: PLC0415
        RoundStatus,
        SceneRoundStartReason,
    )
    from world.scenes.models import Scene  # noqa: PLC0415

    scene = Scene.objects.filter(pk=scene_id).select_related("location").first()
    if scene is None:
        return anima_cost

    has_active_combat = CombatEncounter.objects.filter(
        scene=scene,
        status__in=[
            RoundStatus.DECLARING,
            RoundStatus.RESOLVING,
            RoundStatus.BETWEEN_ROUNDS,
        ],
    ).exists()
    has_danger_round = False
    if scene.location is not None:
        has_danger_round = scene.scene_rounds.filter(
            start_reason=SceneRoundStartReason.DANGER,
            status__in=[
                RoundStatus.DECLARING,
                RoundStatus.RESOLVING,
                RoundStatus.BETWEEN_ROUNDS,
            ],
        ).exists()
    if not has_active_combat and not has_danger_round:
        return 0
    return anima_cost


def preview_resonance_pull(  # noqa: PLR0913
    character_sheet: CharacterSheet,
    tier: int,
    threads: list[Thread],
    *,
    combat_encounter: CombatEncounter | None = None,
    scene_id: int | None = None,
    excluded_kinds: frozenset[str] | None = None,
    target: ObjectDB | None = None,
    technique: Technique | None = None,
    burn_resonance: ResonanceModel | None = None,
    payers: Mapping[int, ResonanceModel] | None = None,
    with_options: bool = True,
) -> PullPreviewResult:
    """Read-only preview of a resonance pull (Spec A §5.6).

    ``technique`` (#4736): the technique the pull rides. When given, the result's
    ``burn`` carries the burn ceiling (from the technique's runtime intensity, capped
    by the balance left after the pull's cost) and what one burned point is worth, for
    ``burn_resonance`` (the only paying resonance when the pull has one, #5066).

    ``payers`` (#5123) names the resonance paying for each thread, keyed by thread id; a
    thread it leaves out is paid by its leading resonance. The result's ``per_thread``
    lists, for every pulled thread, each resonance the character holds as a payer option;
    ``with_options=False`` leaves ``per_thread`` empty, for a caller that only reads
    ``affordable`` (the options cost a full effect resolution per held resonance per thread).

    Validates ownership + non-empty threads (the threads may be of any resonances; each
    is paid by its payer, #5066, #5123), computes the
    tier's resonance / anima cost, reads current balances WITHOUT locking or
    debiting, and resolves per-thread effects across tiers 0..tier using the
    same helper that the commit path uses. Never mutates state.

    ``combat_encounter`` controls the VITAL_BONUS ``inactive`` flag per
    §3.8 + §7.4. ``capped_intensity`` is True when the summed
    INTENSITY_BUMP across resolved effects would exceed the highest
    authored IntensityTier threshold.

    Args:
        character_sheet: Character whose balances the preview reads.
        tier: 1..3, the pull intensity tier.
        threads: Non-empty list of owned threads, of any resonances.
        payers: Thread id -> the resonance paying for that thread; omitted threads are
            paid by their leading resonance.
        combat_encounter: Provided for combat-context previews; ``None``
            for ephemeral / RP previews.
        scene_id: When provided (#1919), the preview computes the combat/DANGER
            state on the scene and returns ``anima_cost=0`` when the anima cost
            is waived (no active combat encounter or DANGER round). When
            ``None``, the standard formula applies.
        excluded_kinds: When set (#1919), the preview validates that no pulled
            thread has a ``target_kind`` in the set and raises
            ``InvalidImbueAmount`` early. Social-action previews pass
            ``frozenset({TargetKind.GIFT})`` so a GIFT thread is rejected at
            preview time (matching the charge-time behavior).
        target: The live target this pull's action would be directed at
            (#2035), fed through to ``resolve_pull_effects`` exactly as the
            commit path (``spend_resonance_for_pull``) does — so a
            relationship-bond/Court-regard modulated amount is visible in the
            preview instead of only appearing at commit time. ``None`` (the
            default) reproduces the prior byte-identical, unmodulated preview.

    Returns:
        PullPreviewResult with resonance_cost, anima_cost, affordable,
        resolved_effects, capped_intensity.

    Raises:
        InvalidImbueAmount: empty threads, an ownership mismatch, or
            a thread whose ``target_kind`` is in ``excluded_kinds``.
    """
    if not threads:
        msg = "Must pull at least one thread."
        raise InvalidImbueAmount(msg)

    _validate_pull_threads(threads, character_sheet, excluded_kinds)

    totals = pull_cost_totals(tier, len(threads))
    anima_cost = totals.anima

    # #1919: Anima waiver for social-action previews. When scene_id is provided,
    # check whether the scene is high-stakes (active combat or DANGER round).
    # If not, the anima cost is waived (zeroed).
    anima_cost = _check_anima_waiver(scene_id, anima_cost)

    # Balances — no locks, no debit. Each paying resonance must cover its own threads.
    costs = pull_resonance_costs(tier, threads, payers)
    balances = dict(
        CharacterResonance.objects.filter(
            character_sheet=character_sheet, resonance_id__in=costs
        ).values_list("resonance_id", "balance")
    )
    anima = CharacterAnima.objects.filter(character=character_sheet).first()
    current_anima = anima.current if anima else 0

    affordable = (
        all(balances.get(rid, 0) >= cost for rid, cost in costs.items())
        and current_anima >= anima_cost
    )

    in_combat = combat_encounter is not None
    kindled = pull_kindled_tiers(character_sheet)
    resolved = resolve_pull_effects(
        threads,
        tier,
        in_combat=in_combat,
        target=target,
        character_sheet=character_sheet,
        payers=payers,
        kindled=kindled,
    )
    resolved = _fold_distinction_pull_bonus(
        resolved, character_sheet=character_sheet, threads=threads, payers=payers
    )

    # Cap detection: sum all INTENSITY_BUMP scaled_values, compare against
    # highest IntensityTier.threshold. If no IntensityTier row exists we
    # cannot detect the cap — return False (defensive).
    total_intensity_bump = sum(
        r.scaled_value for r in resolved if r.kind == EffectKind.INTENSITY_BUMP
    )
    highest_tier = IntensityTier.objects.order_by("-threshold").first()
    capped_intensity = highest_tier is not None and total_intensity_bump > highest_tier.threshold

    if burn_resonance is None:
        pulled = {payer.pk: payer for payer in (pull_payer(thread, payers) for thread in threads)}
        burn_resonance = next(iter(pulled.values())) if len(pulled) == 1 else None
    burn = None
    if technique is not None and burn_resonance is not None:
        from world.magic.services.burn import preview_burn  # noqa: PLC0415

        burn = preview_burn(
            character_sheet, burn_resonance, technique, costs.get(burn_resonance.pk, 0)
        )

    return PullPreviewResult(
        resonance_cost=totals.resonance,
        anima_cost=anima_cost,
        affordable=affordable,
        resolved_effects=resolved,
        capped_intensity=capped_intensity,
        burn=burn,
        per_thread=(
            _payer_options_per_thread(
                character_sheet, tier, threads, in_combat=in_combat, target=target, kindled=kindled
            )
            if with_options
            else []
        ),
    )


def _payer_options_per_thread(  # noqa: PLR0913 - one preview's whole resolution context
    character_sheet: CharacterSheet,
    tier: int,
    threads: list[Thread],
    *,
    in_combat: bool,
    target: ObjectDB | None,
    kindled: Mapping[int, KindledStrengthTier],
) -> list[ThreadPayerPreview]:
    """Every held resonance as a payer option for each pulled thread (#5123).

    Each option's ``affordable`` prices that one thread alone, not the whole pull.

    One thread's option is what paying with that resonance alone would cost and whether
    its balance covers it, the perks it would resolve (the payer's, at its level read) and
    the level they are read at. A resonance the thread holds no row for lists no perks and
    reads the thread's own level. A kindled resonance's option carries its strength (#5124) and
    its perks at the higher level that strength reads; ``level_read`` stays the thread's real
    read, since players never see the pull levels.
    """
    each = get_pull_cost(tier, None).resonance_cost
    held = list(
        CharacterResonance.objects.filter(character_sheet=character_sheet)
        .select_related("resonance")
        .order_by("resonance__name")
    )
    return [
        ThreadPayerPreview(
            thread_id=thread.pk,
            options=_options_for_thread(
                character_sheet, tier, thread, held, each, in_combat, target, kindled
            ),
        )
        for thread in threads
    ]


def _options_for_thread(  # noqa: PLR0913 - one preview row's whole resolution context
    character_sheet: CharacterSheet,
    tier: int,
    thread: Thread,
    held: list[CharacterResonance],
    each: int,
    in_combat: bool,
    target: ObjectDB | None,
    kindled: Mapping[int, KindledStrengthTier],
) -> list[PayerOption]:
    """One thread's payer options, the stronger one marked (#5231).

    Each option reads the thread at its own level and, kindled, at the boosted level
    ``_kindled_level`` gives it. Among the options that bring perks, the one whose boosted
    level is strictly the highest, and above its own unboosted level, is the stronger one; a
    tie marks none, and an option with no perks never competes.
    """
    perk_levels = [payer_level_read(thread, cr.resonance) for cr in held]
    reads = [thread.level if level is None else level for level in perk_levels]
    # Only a payer that brings perks competes for the mark: one the thread holds no row for,
    # or a row of nothing, reads the thread's own level but gives nothing to read higher.
    boosted = [
        _kindled_level(read, cr.resonance, kindled, thread) if perk_level is not None else None
        for cr, read, perk_level in zip(held, reads, perk_levels, strict=True)
    ]
    stronger = stronger_marks(boosted, reads)
    return [
        PayerOption(
            resonance=cr.resonance,
            cost=each,
            balance=cr.balance,
            affordable=cr.balance >= each,
            effects=_effects_if_paid_by(
                character_sheet, tier, thread, cr.resonance, in_combat, target, kindled
            ),
            level_read=reads[i],
            kindled_strength=kindled.get(cr.resonance_id),
            stronger=stronger[i],
        )
        for i, cr in enumerate(held)
    ]


def _effects_if_paid_by(  # noqa: PLR0913 - one preview row's whole resolution context
    character_sheet: CharacterSheet,
    tier: int,
    thread: Thread,
    payer: ResonanceModel,
    in_combat: bool,
    target: ObjectDB | None,
    kindled: Mapping[int, KindledStrengthTier],
) -> list[ResolvedPullEffect]:
    """What pulling ``thread`` paid by ``payer`` alone would deliver: its perks plus the
    distinction bonus on that payer, exactly as ``spend_resonance_for_pull`` resolves them."""
    payers = {thread.pk: payer}
    resolved = resolve_pull_effects(
        [thread],
        tier,
        in_combat=in_combat,
        target=target,
        character_sheet=character_sheet,
        payers=payers,
        kindled=kindled,
    )
    return _fold_distinction_pull_bonus(
        resolved, character_sheet=character_sheet, threads=[thread], payers=payers
    )


#: The effect kinds a ``CombatPullResolvedEffect`` may carry a narrative snippet for; the
#: model's per-kind payload constraints require it empty on every numeric kind.
_SNIPPET_KINDS_ON_COMBAT_ROW = frozenset(
    {EffectKind.NARRATIVE_ONLY, EffectKind.CORRUPTION_RESISTANCE}
)


def _kindled_rank(payer: ResonanceModel, kindled: Mapping[int, KindledStrengthTier] | None) -> int:
    """The strength rank the payer drew with (#5124), 0 when it was not kindled."""
    tier = kindled.get(payer.pk) if kindled else None
    return tier.rank if tier is not None else 0


def _persist_combat_pull(  # noqa: PLR0913
    *,
    ctx: PullActionContext,
    tier: int,
    threads: list[Thread],
    resolved: list[ResolvedPullEffect],
    resonance_cost: int,
    anima_total: int,
    resonance_burned: int = 0,
    burned_resonance: ResonanceModel | None = None,
    burn_valuation: BurnValuation | None = None,
    burned_for: str = "",
    payers: Mapping[int, ResonanceModel] | None = None,
    kindled: Mapping[int, KindledStrengthTier] | None = None,
) -> None:
    """Write the CombatPull + CombatPullResolvedEffect rows for a combat pull.

    Combat-context only; the caller branches on ``ctx.combat_encounter is not
    None`` before invoking this.
    """
    from world.combat.models import (  # noqa: PLC0415
        CombatPull,
        CombatPullResolvedEffect,
        CombatPullThread,
    )

    encounter = ctx.combat_encounter
    participant = ctx.participant
    assert encounter is not None  # noqa: S101
    assert participant is not None  # noqa: S101
    pull = CombatPull.objects.create(
        participant=participant,
        encounter=encounter,
        round_number=encounter.round_number,
        tier=tier,
        resonance_spent=resonance_cost,
        anima_spent=anima_total,
        resonance_burned=resonance_burned,
        burned_resonance=burned_resonance if resonance_burned > 0 else None,
        burn_valued_points=burn_valuation.valued_points if burn_valuation else 0,
        burn_strain_units=burn_valuation.strain_units if burn_valuation else 0,
        burn_hasty_fall=burn_valuation.hasty_fall if burn_valuation else False,
        burned_for=burned_for,
    )
    CombatPullThread.objects.bulk_create(
        CombatPullThread(
            pull=pull,
            thread=thread,
            paying_resonance_id=pull_payer(thread, payers).pk,
            kindled_strength=_kindled_rank(pull_payer(thread, payers), kindled),
        )
        for thread in threads
    )
    for r in resolved:
        # ``ASSUME_ALTERNATE_SELF`` is applied at cast resolution (a transformative
        # side-effect of the technique), never at combat-pull commit time, and
        # ``CombatPullResolvedEffect`` has no ``target_form`` column — snapshotting
        # it here would silently drop the form reference and write dead data. Skip
        # it from the combat snapshot (#1604).
        if r.kind == EffectKind.ASSUME_ALTERNATE_SELF:
            continue
        CombatPullResolvedEffect.objects.create(
            pull=pull,
            kind=r.kind,
            authored_value=r.authored_value,
            level_multiplier=r.level_multiplier,
            scaled_value=r.scaled_value,
            vital_target=r.vital_target,
            source_thread=r.source_thread,
            source_thread_level=r.source_thread_level,
            source_tier=r.source_tier,
            granted_capability=r.granted_capability,
            capability_grant_value=r.capability_grant_value,
            # Only the kinds whose payload constraint allows prose keep their snippet; a
            # numeric perk's snippet is flavour text the scene path shows, and the row's
            # CHECK constraint requires it empty (#5123).
            narrative_snippet=(
                r.narrative_snippet if r.kind in _SNIPPET_KINDS_ON_COMBAT_ROW else ""
            ),
            resistance_damage_type=r.resistance_damage_type,
        )


def _validate_pull_threads_for_commit(
    threads: list[Thread],
    character_sheet: CharacterSheet,
    action_context: PullActionContext,
) -> None:
    """Validate ownership, anchor involvement, and facet items (any mix of resonances).

    Raises ``InvalidImbueAmount``, ``CovenantRoleNotEngagedError``, or
    ``NoMatchingWornFacetItemsError`` on the first failing thread.
    """
    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if not _anchor_in_action(t, action_context):
            if t.target_kind == TargetKind.COVENANT_ROLE:
                raise CovenantRoleNotEngagedError
            msg = "Thread anchor is not involved in this action."
            raise InvalidImbueAmount(msg)
        if (
            t.target_kind == TargetKind.FACET
            and not character_sheet.character.equipped_items.item_facets_for(t.target_facet)
        ):
            raise NoMatchingWornFacetItemsError


def _lock_pull_resonances(  # noqa: PLR0913 - the pull's whole payer declaration
    character_sheet: CharacterSheet,
    tier: int,
    threads: list[Thread],
    burn: int,
    burn_resonance: ResonanceModel | None,
    payers: Mapping[int, ResonanceModel] | None = None,
) -> tuple[dict[int, int], dict[int, CharacterResonance]]:
    """Lock and check every resonance a pull spends; ``(cost by resonance id, rows)``.

    Each thread pays the tier's resonance cost from its payer (#5123: the resonance picked
    for it, else its leading one); a burn comes from the one paying resonance it names
    (#5066, maintainer ruling 2026-11-11). The rows are
    locked with ``select_for_update`` so concurrent ephemeral pulls cannot both pass the
    balance check against an unlocked read and double-spend, in resonance order so two
    pulls over the same resonances cannot deadlock. (The combat path is also gated by the
    (participant, round_number) unique key; ephemeral pulls have no such constraint.)

    Raises:
        InvalidImbueAmount: A burn that names no resonance.
        PullValidationError: A burn whose resonance is not one the pull pays with.
        ResonanceInsufficient: A resonance whose balance is below what it must pay.
    """
    costs = pull_resonance_costs(tier, threads, payers)
    if burn > 0:
        if burn_resonance is None:
            msg = "Name which of the paying resonances to burn."
            raise InvalidImbueAmount(msg)
        if burn_resonance.pk not in costs:
            msg = "The burn must come from a resonance you are paying with."
            raise PullValidationError(msg)
        costs[burn_resonance.pk] += burn
    held = {
        cr.resonance_id: cr
        for cr in CharacterResonance.objects.select_for_update()
        .filter(character_sheet=character_sheet, resonance_id__in=costs)
        .order_by("resonance_id")
    }
    for resonance_id, needed in costs.items():
        cr = held.get(resonance_id)
        balance = cr.balance if cr is not None else 0
        if balance < needed:
            name = next(
                payer.name
                for payer in (pull_payer(t, payers) for t in threads)
                if payer.pk == resonance_id
            )
            msg = f"Need {needed} {name} resonance, have {balance}."
            raise ResonanceInsufficient(msg)
    return costs, held


@transaction.atomic
def spend_resonance_for_pull(  # noqa: PLR0913, C901
    character_sheet: CharacterSheet,
    tier: int,
    threads: list[Thread],
    action_context: PullActionContext,
    beseech_bonus_thread_id: int | None = None,
    beseech_bonus: int = 0,
    anima_cost_override: int | None = None,
    burn: int = 0,
    burn_resonance: ResonanceModel | None = None,
    burn_valuation: BurnValuation | None = None,
    burned_for: str = "",
    payers: Mapping[int, ResonanceModel] | None = None,
    worth_by_affinity: Mapping[int, int] | None = None,
) -> ResonancePullResult:
    """Atomic pull commit (Spec A §5.4 + §7.4).

    Validates ownership and anchor involvement; debits each thread's tier cost from its
    payer (the resonance picked for it in ``payers``, else its leading one; the threads
    may mix payers, #5066, #5123, maintainer ruling 2026-11-11),
    all or nothing, plus the anima total; resolves per-thread effects across
    tiers 0..tier; and either persists a ``CombatPull`` (combat context) or
    returns the resolved effects ephemerally (RP context). VITAL_BONUS rows
    are flagged ``inactive`` in ephemeral context with ``scaled_value=0`` —
    full cost is still paid (Spec §7.4 lines 1981–1989).

    Args:
        character_sheet: Character paying the cost.
        tier: 1..3, the pull intensity tier.
        threads: Non-empty list of owned threads, of any resonances.
        action_context: PullActionContext describing the action.
        beseech_bonus_thread_id: PK of the thread whose effective level gets the
            emergency thread-bond draw bonus for this resolution only (#1718).
        beseech_bonus: The bonus amount to apply to that thread's effective level.
        anima_cost_override: When set to 0, the anima cost is waived before the
            balance check — so a player with 0 anima can still pull in a low-stakes
            social context (#1919). The ``CharacterAnima`` lock query is skipped
            entirely and ``anima_spent`` reflects 0. When ``None`` (default), the
            existing per-spec formula applies.
        burn: Resonance burned on top of the pull for strain (#4736): the REACHED
            amount from ``resolve_resonance_burn``, debited with the pull under the
            same lock and recorded on ``CombatPull.resonance_burned``. The burned
            resonance's balance must cover its threads' cost plus the burn, or nothing
            is debited.
        burn_resonance: The paying resonance the burn comes from (#5066); required with
            a burn, and it must be one of the pull's payers.
        payers: Thread id -> the resonance paying for that thread (#5123); a thread not
            named is paid by its leading resonance. A combat pull records each payer on
            its ``CombatPullThread`` row.
        worth_by_affinity: Affinity id -> the worth in percent a caller already rolled for
            it (#5308), so one cast never rolls an affinity twice; every other paying
            affinity rolls its own check here. Every effect a thread bought is scaled by its
            payer affinity's worth before it is persisted or returned.
        burn_valuation: What the burn is worth, valued at declaration; a combat pull
            stores it so the action reads it at resolution without re-valuing.
        burned_for: The declared action a combat burn strains (``PullBurnAction``);
            the caller passes it whenever a burn was asked for, even one that reached
            nothing, and blank otherwise.

    Returns:
        ResonancePullResult with resonance_spent, anima_spent, resolved_effects.

    Raises:
        InvalidImbueAmount: empty threads, an ownership mismatch, an anchor that is not
            in-action, or a burn that names no resonance.
        PullValidationError: a burn whose resonance is not one of the pull's payers.
        ResonanceInsufficient: a resonance's balance below its cost, or insufficient
            anima.
    """
    from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

    if character_sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    if not threads:
        msg = "Must pull at least one thread."
        raise InvalidImbueAmount(msg)

    totals = pull_cost_totals(tier, len(threads))

    _validate_pull_threads_for_commit(threads, character_sheet, action_context)

    burn = max(burn, 0)
    costs, held = _lock_pull_resonances(
        character_sheet, tier, threads, burn, burn_resonance, payers
    )

    # Anima cost: every pulled thread pays its tier's share, the first included (#5066:
    # a pull lasts until her next turn and boosts every use it relates to).
    # #1919: social-action pulls may waive anima entirely when no combat encounter
    # or DANGER round is active — anima_cost_override=0 zeroes the cost before the
    # balance check and skips the lock query entirely.
    anima_total = totals.anima
    if anima_cost_override is not None:
        anima_total = anima_cost_override
    if anima_total > 0:
        anima = CharacterAnima.objects.select_for_update().get(
            character=character_sheet,
        )
        if anima.current < anima_total:
            msg = "Insufficient anima for this pull."
            raise ResonanceInsufficient(msg)
    else:
        anima = None

    in_combat = action_context.combat_encounter is not None
    kindled = pull_kindled_tiers(character_sheet, action_context.participant)
    resolved = resolve_pull_effects(
        threads,
        tier,
        in_combat=in_combat,
        target=action_context.target,
        beseech_bonus_thread_id=beseech_bonus_thread_id,
        beseech_bonus=beseech_bonus,
        character_sheet=character_sheet,
        payers=payers,
        kindled=kindled,
    )
    # The distinction's flat bonus belongs to the pull as a whole, not to one thread's payer,
    # so the worth scales the thread effects only (#5308).
    with_bonus = _fold_distinction_pull_bonus(
        resolved, character_sheet=character_sheet, threads=threads, payers=payers
    )
    worth = _pull_worth_by_affinity(
        character_sheet, threads, action_context, payers, worth_by_affinity
    )
    resolved = [*_scaled_by_worth(resolved, payers, worth), *with_bonus[len(resolved) :]]

    applicable = [e for e in resolved if not e.inactive]
    # A thread paid by a resonance it holds no row for is an ordinary pull with no perks
    # (#5123, ruling 13): the player chose it, so an empty effect list is not a refusal.
    perkless = any(payer_level_read(t, pull_payer(t, payers)) is None for t in threads)
    if not applicable and not perkless:
        msg = "This pull would have no effect on that action."
        raise InvalidImbueAmount(msg)

    # Persist combat pull FIRST so the unique-key check fires before any
    # debit hits the DB. This keeps the in-memory cr / anima instances
    # consistent with the DB on failure — if persist raises IntegrityError,
    # no balance was mutated and the SharedMemoryModel cache stays correct.
    # The select_for_update locks above are still held through this INSERT.
    if in_combat:
        _persist_combat_pull(
            ctx=action_context,
            tier=tier,
            threads=threads,
            resolved=resolved,
            resonance_cost=totals.resonance,
            anima_total=anima_total,
            resonance_burned=burn,
            burned_resonance=burn_resonance,
            burn_valuation=burn_valuation,
            burned_for=burned_for,
            payers=payers,
            kindled=kindled,
        )
    # Debit only after persistence succeeded (mutates SharedMemoryModel-cached
    # instances in place).
    for resonance_id, spent in costs.items():
        cr = held[resonance_id]
        cr.balance -= spent
        cr.save(update_fields=["balance"])
    if anima_total:
        anima.current -= anima_total
        anima.save(update_fields=["current"])

    # Invalidate the per-character handler caches so the next read picks
    # up the new balance and (for combat) the new active CombatPull row.
    character_sheet.character.resonances.invalidate()
    character_sheet.character.combat_pulls.invalidate()

    # Spec §5.8 + §7.4: commit_combat_pull feeds into the same recompute
    # that round-advance uses, so MAX_HEALTH pulls flow through immediately.
    # Ephemeral RP pulls have no max-health consumer (§3.8), so skip.
    if in_combat:
        recompute_max_health_with_threads(character_sheet)

    # #2840: non-combat CAPABILITY_GRANT effects are persisted via a Thread
    # Surge condition (SCENE duration) using the standard condition capability
    # path. The frozen curved value is carried as the condition's severity;
    # ConditionCapabilityEffect(value=1, scales_with_severity=True) on the
    # template means the oracle computes int(1 * severity) = the frozen value.
    if not in_combat:
        _apply_non_combat_capability_grants(character_sheet, resolved)

    # Phase 12-future: emit ThreadsPulled audit event when the event class
    # exists (spec §5.4 step 7). Currently a no-op.

    return ResonancePullResult(
        resonance_spent=totals.resonance,
        anima_spent=anima_total,
        resolved_effects=resolved,
        resonance_burned=burn,
        worth_by_affinity=worth,
    )


def _apply_non_combat_capability_grants(
    character_sheet: CharacterSheet,
    resolved: list[ResolvedPullEffect],
) -> None:
    """Apply a Thread Surge condition for non-combat CAPABILITY_GRANT effects (#2840).

    Uses the standard condition capability path: the Thread Surge template carries
    ``ConditionCapabilityEffect(value=1, scales_with_severity=True)`` rows, and the
    condition is applied with ``severity = MAX frozen curved value`` across the
    pull's CAPABILITY_GRANT effects. The oracle computes
    ``int(1 * effective_severity)`` = the frozen value via ``get_capability_status``.

    All capabilities from one pull share the same severity (the MAX across the
    pull's effects). This is a known limitation when a single pull grants multiple
    capabilities with different curved values — the common case (one capability)
    is exact.
    """
    from world.conditions.models import ConditionCapabilityEffect  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.magic.factories import ensure_thread_surge_content  # noqa: PLC0415

    cap_effects = [
        eff
        for eff in resolved
        if eff.kind == EffectKind.CAPABILITY_GRANT
        and eff.granted_capability is not None
        and eff.capability_grant_value is not None
        and eff.capability_grant_value > 0
    ]
    if not cap_effects:
        return

    template = ensure_thread_surge_content()
    if template is None:
        return

    # Ensure the template has a ConditionCapabilityEffect row for each
    # capability being granted. These are idempotent (get_or_create) — the
    # effect row persists on the template but only fires when an instance
    # is active with scales_with_severity=True.
    for eff in cap_effects:
        ConditionCapabilityEffect.objects.get_or_create(
            condition=template,
            capability=eff.granted_capability,
            defaults={"value": 1, "scales_with_severity": True},
        )

    # Apply with severity = MAX frozen value across all CAPABILITY_GRANT effects.
    severity = max(eff.capability_grant_value for eff in cap_effects)
    character = character_sheet.character
    apply_condition(
        character,
        template,
        severity=severity,
        source_character=character,
        source_description="Thread pull capability surge",
    )
