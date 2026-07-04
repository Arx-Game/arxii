"""Resonance currency service functions: grant, imbue, and pull (Spec A §3.1/3.2/5.4/7.4)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import ACCELERATED_GAIN_SOURCES, EffectKind, GainSource, TargetKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    CovenantRoleNotEngagedError,
    InvalidImbueAmount,
    NoMatchingWornFacetItemsError,
    ResonanceInsufficient,
)
from world.magic.models import (
    CharacterAnima,
    CharacterResonance,
    IntensityTier,
    ResonanceGrant,
    Thread,
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
)
from world.magic.types import (
    PullPreviewResult,
    ResolvedPullEffect,
    ResonancePullResult,
    ThreadImbueResult,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.distinctions.models import CharacterDistinction
    from world.items.models import ItemFacet
    from world.magic.models import (
        DramaticMomentTag,
        EntryFlourishRecord,
        PoseEndorsement,
        Resonance as ResonanceModel,
        SanctumDetails,
        SceneEntryEndorsement,
        StylePresentationEndorsement,
    )
    from world.magic.types import PullActionContext
    from world.missions.models import MissionDeedRewardLine
    from world.projects.models import Project


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
    if source in (GainSource.STAFF_GRANT, GainSource.MISSION_REPORT, GainSource.STAKE_REWARD):
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


@transaction.atomic
def spend_resonance_for_imbuing(  # noqa: C901
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

    starting_level = thread.level
    if amount:
        cr.balance -= amount
        thread.developed_points += amount

    blocked_by: str = "NONE"
    imbue_multiplier = get_imbue_cost_multiplier(thread.target_kind)
    while True:
        n = thread.level
        next_level = n + 1
        cost = max((n - 9) * 100, 1) * imbue_multiplier  # sub-10 levels cost 1 dp each
        if thread.developed_points < cost:
            if amount == 0:
                blocked_by = "INSUFFICIENT_BUCKET"
            break
        if next_level % 10 == 0:
            unlocked = ThreadLevelUnlock.objects.filter(
                thread=thread,
                unlocked_level=next_level,
            ).exists()
            if not unlocked:
                blocked_by = "XP_LOCK"
                break
        if next_level > cap:
            blocked_by = (
                "PATH_CAP"
                if compute_path_cap(character_sheet) < compute_anchor_cap(thread)
                else "ANCHOR_CAP"
            )
            break
        thread.level = next_level
        thread.developed_points -= cost

    cr.save(update_fields=["balance"])
    thread.save(update_fields=["level", "developed_points"])

    recompute_max_health_with_threads(character_sheet)

    from world.covenants.discovery import fire_variant_discoveries  # noqa: PLC0415

    fire_variant_discoveries(thread=thread, starting_level=starting_level, new_level=thread.level)

    return ThreadImbueResult(
        resonance_spent=amount,
        developed_points_added=amount,
        levels_gained=thread.level - starting_level,
        new_level=thread.level,
        new_developed_points=thread.developed_points,
        blocked_by=blocked_by,  # type: ignore[arg-type]
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
    }
)


def _anchor_in_action(thread: Thread, ctx: PullActionContext) -> bool:
    """Return True iff ``thread``'s anchor is involved in the action (Spec A §5.2).

    Relationship anchors are always considered in-action (player asserts
    involvement). Other kinds are matched against the explicit ``involved_*``
    tuples on the context — the caller is responsible for populating those.

    COVENANT_ROLE threads gate on engagement: the character must currently be
    fulfilling the role for one of their covenants (Slice A §3.6).
    """
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


def resolve_pull_effects(
    threads: list[Thread],
    tier: int,
    *,
    in_combat: bool,
) -> list[ResolvedPullEffect]:
    """Resolve every (thread × effect_tier 0..tier) pair into ResolvedPullEffect rows.

    Implements Spec A §5.4 step 3. VITAL_BONUS rows in non-combat (ephemeral)
    context are flagged ``inactive`` with ``scaled_value=0`` per spec §7.4
    lines 1981–1989; the caller still pays full cost.
    """
    resolved: list[ResolvedPullEffect] = []
    for t in threads:
        multiplier = max(1, t.level // 10)
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
                    base_scaled = (
                        int((authored or 0) * multiplier * worn_aggregate)
                        if has_numeric_payload
                        else None
                    )
                else:
                    base_scaled = (authored or 0) * multiplier if has_numeric_payload else None

                # VITAL_BONUS and RESISTANCE are combat-only consumers: their snapshot
                # lives on CombatPullResolvedEffect and is read on the combat damage
                # path, so ephemeral (RP) pulls flag them inactive (cost still paid).
                inactive = (
                    row.effect_kind in (EffectKind.VITAL_BONUS, EffectKind.RESISTANCE)
                    and not in_combat
                )
                resolved.append(
                    ResolvedPullEffect(
                        kind=row.effect_kind,
                        authored_value=authored,
                        level_multiplier=multiplier,
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
    (``magic/services/techniques.py``). Folds the identical bonus into the pull's own
    magnitude once per pull (not per thread/tier — every thread here shares ``resonance`` by
    construction) so a standalone thread-pull is boosted identically to a cast (#1834 Task 7).
    No-op (returns ``resolved`` unchanged) when there is no matching modifier.
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
            source_thread=threads[0],
            source_thread_level=threads[0].level,
            source_tier=0,
            granted_capability=None,
            narrative_snippet="",
            target_form=None,
            resistance_damage_type=None,
        ),
    ]


def preview_resonance_pull(
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    tier: int,
    threads: list[Thread],
    *,
    combat_encounter: CombatEncounter | None = None,
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

    Returns:
        PullPreviewResult with resonance_cost, anima_cost, affordable,
        resolved_effects, capped_intensity.

    Raises:
        InvalidImbueAmount: empty threads, ownership / resonance mismatch.
    """
    if not threads:
        msg = "Must pull at least one thread."
        raise InvalidImbueAmount(msg)

    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if t.resonance_id != resonance.pk:
            msg = "Thread does not share the chosen resonance."
            raise InvalidImbueAmount(msg)

    cost = get_pull_cost(tier, None)
    n_threads = len(threads)
    anima_cost = cost.anima_per_thread * max(0, n_threads - 1)

    # Balances — no locks, no debit.
    cr = CharacterResonance.objects.filter(
        character_sheet=character_sheet,
        resonance=resonance,
    ).first()
    balance = cr.balance if cr else 0
    anima = CharacterAnima.objects.filter(character=character_sheet.character).first()
    current_anima = anima.current if anima else 0

    affordable = balance >= cost.resonance_cost and current_anima >= anima_cost

    in_combat = combat_encounter is not None
    resolved = resolve_pull_effects(threads, tier, in_combat=in_combat)
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
            narrative_snippet=r.narrative_snippet,
            resistance_damage_type=r.resistance_damage_type,
        )


@transaction.atomic
def spend_resonance_for_pull(  # noqa: C901, PLR0912
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    tier: int,
    threads: list[Thread],
    action_context: PullActionContext,
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
    anima_total = cost.anima_per_thread * max(0, n_threads - 1)
    anima = CharacterAnima.objects.select_for_update().get(
        character=character_sheet.character,
    )
    if anima.current < anima_total:
        msg = "Insufficient anima for this pull."
        raise ResonanceInsufficient(msg)

    in_combat = action_context.combat_encounter is not None
    resolved = resolve_pull_effects(threads, tier, in_combat=in_combat)
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
