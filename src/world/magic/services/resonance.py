"""Resonance currency service functions: grant, imbue, and pull (Spec A §3.1/3.2/5.4/7.4)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
import logging
import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.classes.services import is_crossing_level
from world.magic.constants import ACCELERATED_GAIN_SOURCES, EffectKind, GainSource, TargetKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    CovenantRoleNotEngagedError,
    InvalidImbueAmount,
    MagicError,
    NoMatchingWornFacetItemsError,
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
from world.magic.services.pull_effects import get_pull_effects_for_thread
from world.magic.services.threads import (
    compute_anchor_cap,
    compute_effective_cap,
    compute_path_cap,
    get_imbue_cost_multiplier,
    get_pull_cost,
    recompute_max_health_with_threads,
    thread_level_multiplier,
)
from world.magic.types import (
    PullPreviewResult,
    ResolvedPullEffect,
    ResonancePullResult,
    ThreadImbueResult,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.action_points.models import ActionPointPool
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.distinctions.models import CharacterDistinction
    from world.items.models import ItemFacet, Mantle
    from world.magic.models import (
        DramaticMomentTag,
        EntryFlourishRecord,
        PoseEndorsement,
        Resonance as ResonanceModel,
        SanctumDetails,
        SceneEntryEndorsement,
        StylePresentationEndorsement,
    )
    from world.magic.models.power_config import CapabilityPowerConfig
    from world.magic.models.threads import ThreadPullEffect
    from world.magic.types import PullActionContext
    from world.missions.models import MissionDeedRewardLine
    from world.projects.models import Project
    from world.relationships.models import RelationshipCapstone, RelationshipTrackProgress

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
) -> CharacterResonance:
    """Atomically grant resonance AND write the ResonanceGrant ledger row.

    Validates that the typed source kwarg matches the discriminator. When
    ``source`` is one of ``ACCELERATED_GAIN_SOURCES`` (ADR-0041 — the
    perception/presence gain sources), ``amount`` is scaled up by the
    character's summed distinction earn-rate bonus for ``resonance`` before
    it is written; authored/system sources (including DISTINCTION itself)
    are never accelerated.

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
    )

    if source in ACCELERATED_GAIN_SOURCES:
        from world.magic.services.distinction_resonance import (  # noqa: PLC0415
            distinction_earn_rate_for,
        )

        earn_rate_bonus = distinction_earn_rate_for(character_sheet, resonance)
        if earn_rate_bonus > 0:
            amount = int(amount * (1 + earn_rate_bonus / Decimal(100)))

    cr, _ = CharacterResonance.objects.get_or_create(
        character_sheet=character_sheet,
        resonance=resonance,
        defaults={"balance": 0, "lifetime_earned": 0},
    )
    cr.balance += amount
    cr.lifetime_earned += amount
    cr.save(update_fields=["balance", "lifetime_earned"])

    ResonanceGrant.objects.create(
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
    )

    from world.magic.services.aura import (  # noqa: PLC0415
        fire_aura_threshold_crossings,
        recompute_aura,
    )

    # Two separate steps chained here: recompute the aura, then check whether
    # the drift crossed any authored AuraAffinityThreshold (#1737).
    drift = recompute_aura(character_sheet)
    if drift is not None:
        fire_aura_threshold_crossings(character_sheet, drift)

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
        GainSource.PENANCE,
        GainSource.FALL_CONVERSION,
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
}


def _check_imbue_level_advance(  # noqa: PLR0913
    thread: Thread,
    next_level: int,
    cap: int,
    character_sheet: CharacterSheet,
    *,
    amount: int,
    imbue_multiplier: int,
) -> tuple[bool, str, list[str]]:
    """Evaluate whether a thread can advance to ``next_level``.

    Returns ``(should_advance, blocked_by, blocked_requirement_messages)``.
    When ``should_advance`` is ``False``, ``blocked_by`` names the gate that
    stopped advancement (or ``"NONE"`` if the bucket is simply exhausted and
    ``blocked_requirement_messages`` carries crossing-requirement failures.
    """
    cost = max((thread.level - 9) * 100, 1) * imbue_multiplier
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
    if is_crossing_level(next_level):
        from world.progression.services.spends import (  # noqa: PLC0415
            check_requirements_for_thread_crossing,
        )

        threshold = ThreadCrossingThreshold.objects.filter(
            target_kind=thread.target_kind,
            level=next_level,
        ).first()
        if threshold is not None:
            met, failed = check_requirements_for_thread_crossing(
                character_sheet.character, threshold
            )
            if not met:
                return False, "CROSSING_REQUIREMENT", failed
    if next_level > cap:
        blocked_by = (
            "PATH_CAP"
            if compute_path_cap(character_sheet) < compute_anchor_cap(thread)
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


@transaction.atomic
def spend_resonance_for_imbuing(
    character_sheet: CharacterSheet,
    thread: Thread,
    amount: int,
) -> ThreadImbueResult:
    """Deduct resonance balance and greedily advance thread level.

    Spec A §3.2. Cost formula: max((current_level - 9) * 100, 1) dp per level.
    Sub-10 levels each cost 1 dp. Advancement continues until the bucket is
    exhausted, the next level hits an XP-lock gate, or the effective cap is
    reached.

    Args:
        character_sheet: Character performing the imbuing.
        thread: Thread to advance (must be owned by character_sheet).
        amount: Resonance balance to spend (0 = drain existing bucket only).

    Returns:
        ThreadImbueResult dataclass.

    Raises:
        InvalidImbueAmount: If amount < 0 or thread.owner != character_sheet.
        AnchorCapExceeded: If thread is already at effective cap.
        ResonanceInsufficient: If balance < amount.
    """
    from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

    if character_sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    if amount < 0:
        msg = "Imbue amount must be non-negative."
        raise InvalidImbueAmount(msg)
    if thread.owner_id != character_sheet.pk:
        msg = "Character does not own thread."
        raise InvalidImbueAmount(msg)
    cap = compute_effective_cap(thread)
    if thread.level >= cap:
        msg = "Thread already at effective cap."
        raise AnchorCapExceeded(msg)

    cr = CharacterResonance.objects.get(
        character_sheet=character_sheet,
        resonance=thread.resonance,
    )
    if amount and cr.balance < amount:
        msg = "Need " + str(amount) + ", have " + str(cr.balance) + "."
        raise ResonanceInsufficient(msg)

    # AP charge (development time) — flat per rite, Unbound surcharge applies.
    _charge_imbue_ap(character_sheet)

    starting_level = thread.level
    if amount:
        cr.balance -= amount
        thread.developed_points += amount

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
        )
        if not should_advance:
            break
        cost = max((thread.level - 9) * 100, 1) * imbue_multiplier
        thread.level = next_level
        thread.developed_points -= cost

    cr.save(update_fields=["balance"])
    thread.save(update_fields=["level", "developed_points"])

    recompute_max_health_with_threads(character_sheet)

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


def _anchor_in_action(thread: Thread, ctx: PullActionContext) -> bool:  # noqa: PLR0911
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
        return thread.target_technique_id in ctx.involved_techniques
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        sheet = thread.owner
        engaged_roles = sheet.character.covenant_roles.currently_engaged_roles()
        target_pk = thread.target_covenant_role_id
        return any(role.pk == target_pk for role in engaged_roles)
    if thread.target_kind == TargetKind.SANCTUM:
        room_obj_id = thread.target_sanctum_details.feature_instance.room_profile.objectdb_id
        return room_obj_id in ctx.involved_objects
    return False


def _anchor_ambiently_active(  # noqa: PLR0911 — one arm per TargetKind, flat by design
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
        return _relationship_target_present(thread.target_relationship_track, character)
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
    owner_row: RelationshipTrackProgress | RelationshipCapstone | None,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — room-contents check needs the game object
) -> bool:
    """True iff the other party to this relationship is in the acting character's room.

    ``owner_row`` is a RelationshipTrackProgress or a RelationshipCapstone; both carry a
    ``relationship`` FK to CharacterRelationship, whose ``target`` is a CharacterSheet
    (relationships/models.py:323). CharacterSheet shares ObjectDB's pk, so the presence
    check is a pk comparison — no extra fetch.
    """
    location = character.location
    if owner_row is None or location is None:
        return False
    target_pk = owner_row.relationship.target_id
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


def resolve_pull_effects(  # noqa: PLR0913  — thread × effect_tier resolver; both target (#1831) and beseech (#1718) params are required
    threads: list[Thread],
    tier: int,
    *,
    in_combat: bool,
    target: ObjectDB | None = None,
    beseech_bonus_thread_id: int | None = None,
    beseech_bonus: int = 0,
    character_sheet: CharacterSheet | None = None,
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
    """
    from world.magic.services.pull_modulation import apply_target_modulation  # noqa: PLC0415

    # #2730: CAPABILITY_GRANT rows are curved at resolve time using the same
    # apply_capability_curve formula the passive path uses. The power figure
    # is context_free_power (ADR-0169 D6 — capability standing must not
    # flicker based on whether combat is running). Fetched once per sweep.
    power_config, context_free_power = _derive_pull_power(character_sheet)

    resolved: list[ResolvedPullEffect] = []
    for t in threads:
        effective_level = t.level
        if beseech_bonus_thread_id is not None and t.pk == beseech_bonus_thread_id:
            effective_level = t.level + beseech_bonus
        multiplier = thread_level_multiplier(effective_level)
        for effect_tier in range(tier + 1):
            rows = get_pull_effects_for_thread(
                t,
                tier=effect_tier,
                min_thread_level__lte=t.level,
            )
            for row in rows:
                authored = (
                    row.flat_bonus_amount
                    or row.intensity_bump_amount
                    or row.vital_bonus_amount
                    or row.resistance_amount
                )
                # ASSUME_ALTERNATE_SELF, CAPABILITY_GRANT, NARRATIVE_ONLY, and
                # CORRUPTION_RESISTANCE have no numeric payload; their scaled_value
                # must be None. ASSUME_ALTERNATE_SELF derives its runtime stat-suite
                # from the target form's selected combat profile (crit/mid/fail bands).
                # CORRUPTION_RESISTANCE derives its runtime value from
                # CharacterResonance.lifetime_helped (Spec B §10.2) — it is applied
                # directly in accrue_corruption, not via a scaled_value here.
                has_numeric_payload = row.effect_kind not in (
                    EffectKind.ASSUME_ALTERNATE_SELF,
                    EffectKind.CAPABILITY_GRANT,
                    EffectKind.NARRATIVE_ONLY,
                    EffectKind.CORRUPTION_RESISTANCE,
                )

                if t.target_kind == TargetKind.FACET:
                    matching = t.owner.character.equipped_items.item_facets_for(t.target_facet)
                    if not matching:
                        # No worn items bearing this facet — skip this effect row.
                        # Other threads in the outer loop still resolve normally.
                        continue
                    # Decimal(str(...)) coerces in case a multiplier surfaces as
                    # float (e.g. via factory or .values() in test fixtures);
                    # DecimalField normally returns Decimal but this is
                    # belt-and-suspenders.
                    items_aggregate = [
                        (
                            Decimal(str(item_facet.item_instance.quality_tier.stat_multiplier))
                            if item_facet.item_instance.quality_tier is not None
                            else Decimal(1)
                        )
                        * Decimal(str(item_facet.attachment_quality_tier.stat_multiplier))
                        for item_facet in matching
                    ]
                    worn_aggregate = sum(items_aggregate, Decimal(0))
                    # round(), not int() truncation: thread_level_multiplier (#1718)
                    # now returns a fractional Decimal for levels 1-9, and rounding to
                    # the nearest int is fairer to the player than always flooring.
                    base_scaled = (
                        round((authored or 0) * multiplier * worn_aggregate)
                        if has_numeric_payload
                        else None
                    )
                else:
                    # See the FACET-branch comment above re: round() vs int().
                    base_scaled = (
                        round((authored or 0) * multiplier) if has_numeric_payload else None
                    )

                if has_numeric_payload:
                    base_scaled = apply_target_modulation(t, target, row, base_scaled)

                # VITAL_BONUS, RESISTANCE, and CAPABILITY_GRANT are combat-only
                # VITAL_BONUS and RESISTANCE are combat-only consumers: their
                # snapshot lives on CombatPullResolvedEffect and is read on the
                # combat path, so ephemeral (RP) pulls flag them inactive (cost
                # still paid). CAPABILITY_GRANT is now active in non-combat
                # context — the frozen value is persisted via the Thread Surge
                # condition + EphemeralPullCapabilityGrant sidecar (#2840).
                inactive = (
                    row.effect_kind
                    in (
                        EffectKind.VITAL_BONUS,
                        EffectKind.RESISTANCE,
                    )
                    and not in_combat
                )
                # #2730: compute the frozen curved magnitude for CAPABILITY_GRANT.
                # Uses the same apply_capability_curve formula as the passive path
                # (handlers.py:_passive_capability_grants_cache), with
                # context_free_power as the power figure (ADR-0169 D6).
                capability_grant_value = _compute_capability_grant_value(
                    row,
                    inactive=inactive,
                    multiplier=multiplier,
                    power_config=power_config,
                    context_free_power=context_free_power,
                )
                resolved.append(
                    ResolvedPullEffect(
                        kind=row.effect_kind,
                        authored_value=authored,
                        # ResolvedPullEffect.level_multiplier is int-typed (persisted
                        # to CombatPullResolvedEffect.level_multiplier, a
                        # PositiveSmallIntegerField); round() the transient Decimal
                        # multiplier to an int for the snapshot (#1718).
                        level_multiplier=round(multiplier),
                        scaled_value=0 if inactive else base_scaled,
                        vital_target=row.vital_target,
                        source_thread=t,
                        source_thread_level=t.level,
                        source_tier=effect_tier,
                        granted_capability=row.capability_grant,
                        narrative_snippet=row.narrative_snippet,
                        inactive=inactive,
                        inactive_reason=("requires combat context" if inactive else None),
                        target_form=row.target_form,
                        resistance_damage_type=row.resistance_damage_type,
                        capability_grant_value=capability_grant_value,
                    )
                )
    return resolved


def _fold_distinction_pull_bonus(
    resolved: list[ResolvedPullEffect],
    *,
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    threads: list[Thread],
) -> list[ResolvedPullEffect]:
    """Append a synthetic FLAT_BONUS entry for a distinction's resonance-scoped POWER modifier.

    A distinction expresses potency for ``resonance`` by authoring a ``DistinctionEffect`` on
    a POWER-category ``ModifierTarget`` gated by ``target_resonance`` — the same modifier a
    technique cast already reads via ``_derive_power``'s FLAT stage
    (``magic/services/techniques.py``). Folds that one modifier into the pull's own magnitude
    once per pull (not per thread/tier — every thread here shares ``resonance`` by
    construction) (#1834 Task 7). No-op (returns ``resolved`` unchanged) when there is no
    matching modifier.

    Not full parity with a cast: ``_derive_power``'s FLAT stage also sums condition-sourced
    POWER contributions (``get_condition_modifier_breakdown``), which this fold does not
    include — only the distinction-authored ``CharacterModifier`` side.
    """
    from world.mechanics.services import power_flat_bonus_for_resonance  # noqa: PLC0415

    bonus = power_flat_bonus_for_resonance(character_sheet, resonance.pk)
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
            # threads[0] is an arbitrary pick (every thread here shares one resonance, so
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
    resonance: ResonanceModel,
    excluded_kinds: frozenset[str] | None,
) -> None:
    """Validate ownership, same-resonance, and excluded-kinds for pull threads.

    Raises ``InvalidImbueAmount`` on the first failing thread.
    """
    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if t.resonance_id != resonance.pk:
            msg = "Thread does not share the chosen resonance."
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
    resonance: ResonanceModel,
    tier: int,
    threads: list[Thread],
    *,
    combat_encounter: CombatEncounter | None = None,
    scene_id: int | None = None,
    excluded_kinds: frozenset[str] | None = None,
    target: ObjectDB | None = None,
) -> PullPreviewResult:
    """Read-only preview of a resonance pull (Spec A §5.6).

    Validates ownership + same-resonance + non-empty threads, computes the
    tier's resonance / anima cost, reads current balances WITHOUT locking or
    debiting, and resolves per-thread effects across tiers 0..tier using the
    same helper that the commit path uses. Never mutates state.

    ``combat_encounter`` controls the VITAL_BONUS ``inactive`` flag per
    §3.8 + §7.4. ``capped_intensity`` is True when the summed
    INTENSITY_BUMP across resolved effects would exceed the highest
    authored IntensityTier threshold.

    Args:
        character_sheet: Character whose balances the preview reads.
        resonance: Resonance the pull would channel (must match every
            thread).
        tier: 1..3, the pull intensity tier.
        threads: Non-empty list of owned threads matching ``resonance``.
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
        InvalidImbueAmount: empty threads, ownership / resonance mismatch, or
            a thread whose ``target_kind`` is in ``excluded_kinds``.
    """
    if not threads:
        msg = "Must pull at least one thread."
        raise InvalidImbueAmount(msg)

    _validate_pull_threads(threads, character_sheet, resonance, excluded_kinds)

    cost = get_pull_cost(tier, None)
    n_threads = len(threads)
    anima_cost = cost.anima_per_thread * max(0, n_threads - 1)

    # #1919: Anima waiver for social-action previews. When scene_id is provided,
    # check whether the scene is high-stakes (active combat or DANGER round).
    # If not, the anima cost is waived (zeroed).
    anima_cost = _check_anima_waiver(scene_id, anima_cost)

    # Balances — no locks, no debit.
    cr = CharacterResonance.objects.filter(
        character_sheet=character_sheet,
        resonance=resonance,
    ).first()
    balance = cr.balance if cr else 0
    anima = CharacterAnima.objects.filter(character=character_sheet).first()
    current_anima = anima.current if anima else 0

    affordable = balance >= cost.resonance_cost and current_anima >= anima_cost

    in_combat = combat_encounter is not None
    resolved = resolve_pull_effects(
        threads, tier, in_combat=in_combat, target=target, character_sheet=character_sheet
    )
    resolved = _fold_distinction_pull_bonus(
        resolved, character_sheet=character_sheet, resonance=resonance, threads=threads
    )

    # Cap detection: sum all INTENSITY_BUMP scaled_values, compare against
    # highest IntensityTier.threshold. If no IntensityTier row exists we
    # cannot detect the cap — return False (defensive).
    total_intensity_bump = sum(
        r.scaled_value for r in resolved if r.kind == EffectKind.INTENSITY_BUMP
    )
    highest_tier = IntensityTier.objects.order_by("-threshold").first()
    capped_intensity = highest_tier is not None and total_intensity_bump > highest_tier.threshold

    return PullPreviewResult(
        resonance_cost=cost.resonance_cost,
        anima_cost=anima_cost,
        affordable=affordable,
        resolved_effects=resolved,
        capped_intensity=capped_intensity,
    )


def _persist_combat_pull(  # noqa: PLR0913
    *,
    ctx: PullActionContext,
    resonance: ResonanceModel,
    tier: int,
    threads: list[Thread],
    resolved: list[ResolvedPullEffect],
    resonance_cost: int,
    anima_total: int,
) -> None:
    """Write the CombatPull + CombatPullResolvedEffect rows for a combat pull.

    Combat-context only; the caller branches on ``ctx.combat_encounter is not
    None`` before invoking this.
    """
    from world.combat.models import (  # noqa: PLC0415
        CombatPull,
        CombatPullResolvedEffect,
    )

    encounter = ctx.combat_encounter
    participant = ctx.participant
    assert encounter is not None  # noqa: S101
    assert participant is not None  # noqa: S101
    pull = CombatPull.objects.create(
        participant=participant,
        encounter=encounter,
        round_number=encounter.round_number,
        resonance=resonance,
        tier=tier,
        resonance_spent=resonance_cost,
        anima_spent=anima_total,
    )
    pull.threads.set(threads)
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
            narrative_snippet=r.narrative_snippet,
            resistance_damage_type=r.resistance_damage_type,
        )


def _validate_pull_threads_for_commit(
    threads: list[Thread],
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    action_context: PullActionContext,
) -> None:
    """Validate ownership, resonance match, anchor involvement, and facet items.

    Raises ``InvalidImbueAmount``, ``CovenantRoleNotEngagedError``, or
    ``NoMatchingWornFacetItemsError`` on the first failing thread.
    """
    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if t.resonance_id != resonance.pk:
            msg = "Thread does not share the chosen resonance."
            raise InvalidImbueAmount(msg)
        if not _anchor_in_action(t, action_context):
            if t.target_kind == TargetKind.COVENANT_ROLE:
                raise CovenantRoleNotEngagedError
            msg = "Thread anchor is not involved in this action."
            raise InvalidImbueAmount(msg)
        if t.target_kind == TargetKind.FACET:
            if not character_sheet.character.equipped_items.item_facets_for(t.target_facet):
                raise NoMatchingWornFacetItemsError


@transaction.atomic
def spend_resonance_for_pull(  # noqa: PLR0913, C901
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    tier: int,
    threads: list[Thread],
    action_context: PullActionContext,
    beseech_bonus_thread_id: int | None = None,
    beseech_bonus: int = 0,
    anima_cost_override: int | None = None,
) -> ResonancePullResult:
    """Atomic pull commit (Spec A §5.4 + §7.4).

    Validates ownership, resonance match, and anchor involvement; debits the
    per-tier resonance cost + anima total; resolves per-thread effects across
    tiers 0..tier; and either persists a ``CombatPull`` (combat context) or
    returns the resolved effects ephemerally (RP context). VITAL_BONUS rows
    are flagged ``inactive`` in ephemeral context with ``scaled_value=0`` —
    full cost is still paid (Spec §7.4 lines 1981–1989).

    Args:
        character_sheet: Character paying the cost.
        resonance: Resonance shared by every pulled thread.
        tier: 1..3, the pull intensity tier.
        threads: Non-empty list of owned threads matching ``resonance``.
        action_context: PullActionContext describing the action.
        beseech_bonus_thread_id: PK of the thread whose effective level gets the
            emergency thread-bond draw bonus for this resolution only (#1718).
        beseech_bonus: The bonus amount to apply to that thread's effective level.
        anima_cost_override: When set to 0, the anima cost is waived before the
            balance check — so a player with 0 anima can still pull in a low-stakes
            social context (#1919). The ``CharacterAnima`` lock query is skipped
            entirely and ``anima_spent`` reflects 0. When ``None`` (default), the
            existing per-spec formula applies.

    Returns:
        ResonancePullResult with resonance_spent, anima_spent, resolved_effects.

    Raises:
        InvalidImbueAmount: empty threads, ownership / resonance mismatch, or
            an anchor that is not in-action.
        ResonanceInsufficient: balance below cost or insufficient anima.
    """
    from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

    if character_sheet.is_protagonism_locked:
        raise ProtagonismLockedError

    if not threads:
        msg = "Must pull at least one thread."
        raise InvalidImbueAmount(msg)

    cost = get_pull_cost(tier, None)
    n_threads = len(threads)

    _validate_pull_threads_for_commit(threads, character_sheet, resonance, action_context)

    # select_for_update on cr + anima so concurrent ephemeral pulls cannot
    # both pass the balance check against an unlocked read and double-spend.
    # The combat path is also gated by the (participant, round_number) unique
    # key, but ephemeral pulls have no DB-level uniqueness constraint.
    cr = CharacterResonance.objects.select_for_update().get(
        character_sheet=character_sheet,
        resonance=resonance,
    )
    if cr.balance < cost.resonance_cost:
        msg = "Need " + str(cost.resonance_cost) + " resonance, have " + str(cr.balance) + "."
        raise ResonanceInsufficient(msg)

    # Anima cost: per-spec §5.4 lines 1452–1458, anima_per_thread × max(0, n-1).
    # #1919: social-action pulls may waive anima entirely when no combat encounter
    # or DANGER round is active — anima_cost_override=0 zeroes the cost before the
    # balance check and skips the lock query entirely.
    anima_total = cost.anima_per_thread * max(0, n_threads - 1)
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
    resolved = resolve_pull_effects(
        threads,
        tier,
        in_combat=in_combat,
        target=action_context.target,
        beseech_bonus_thread_id=beseech_bonus_thread_id,
        beseech_bonus=beseech_bonus,
        character_sheet=character_sheet,
    )
    resolved = _fold_distinction_pull_bonus(
        resolved, character_sheet=character_sheet, resonance=resonance, threads=threads
    )

    applicable = [e for e in resolved if not e.inactive]
    if not applicable:
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
            resonance=resonance,
            tier=tier,
            threads=threads,
            resolved=resolved,
            resonance_cost=cost.resonance_cost,
            anima_total=anima_total,
        )
    # Debit only after persistence succeeded (mutates SharedMemoryModel-cached
    # instances in place).
    cr.balance -= cost.resonance_cost
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

    # Phase 12-future: emit ThreadsPulled audit event when the event class
    # exists (spec §5.4 step 7). Currently a no-op.

    return ResonancePullResult(
        resonance_spent=cost.resonance_cost,
        anima_spent=anima_total,
        resolved_effects=resolved,
    )
