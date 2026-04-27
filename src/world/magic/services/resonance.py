"""Resonance currency service functions: grant, imbue, and pull (Spec A §3.1/3.2/5.4/7.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import EffectKind, GainSource, TargetKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    ResonanceInsufficient,
)
from world.magic.models import (
    CharacterAnima,
    CharacterResonance,
    IntensityTier,
    ResonanceGrant,
    RoomAuraProfile,
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadPullEffect,
)
from world.magic.services.threads import (
    compute_anchor_cap,
    compute_effective_cap,
    compute_path_cap,
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

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.magic.models import (
        PoseEndorsement,
        Resonance as ResonanceModel,
        SceneEntryEndorsement,
    )
    from world.magic.types import PullActionContext


# =============================================================================
# Phase 11 — Earn / Spend services (Spec A §3.1, §3.2, §3.6, §7.4)
# =============================================================================


@transaction.atomic
def grant_resonance(  # noqa: PLR0913 — typed-FK kwargs are inherently numerous; grouped for readability
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
    amount: int,
    *,
    source: str,
    pose_endorsement: PoseEndorsement | None = None,
    scene_entry_endorsement: SceneEntryEndorsement | None = None,
    room_aura_profile: RoomAuraProfile | None = None,
    staff_account: AccountDB | None = None,
) -> CharacterResonance:
    """Atomically grant resonance AND write the ResonanceGrant ledger row.

    Validates that the typed source kwarg matches the discriminator. Raises
    ValueError for OUTFIT_TRICKLE source — that typed FK ships with the Items system.

    Args:
        character_sheet: The character receiving resonance.
        resonance: The Resonance being granted.
        amount: Positive integer amount to grant.
        source: GainSource discriminator (keyword-only).
        pose_endorsement: Required for POSE_ENDORSEMENT source.
        scene_entry_endorsement: Required for SCENE_ENTRY source.
        room_aura_profile: Required for ROOM_RESIDENCE source.
        staff_account: Optional for STAFF_GRANT source (nullable by design).

    Returns:
        The updated CharacterResonance instance.

    Raises:
        InvalidImbueAmount: If amount <= 0.
        ValueError: If source/kwarg shape is invalid or source is not yet supported.
    """
    if amount <= 0:
        msg = "Resonance grant amount must be positive."
        raise InvalidImbueAmount(msg)

    _validate_grant_source_shape(
        source,
        room_aura_profile=room_aura_profile,
        pose_endorsement=pose_endorsement,
        scene_entry_endorsement=scene_entry_endorsement,
    )

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
        source_room_aura_profile=room_aura_profile,
        source_staff_account=staff_account,
        source_pose_endorsement=pose_endorsement,
        source_scene_entry_endorsement=scene_entry_endorsement,
    )
    return cr


def _validate_grant_source_shape(
    source: str,
    *,
    room_aura_profile: RoomAuraProfile | None,
    pose_endorsement: PoseEndorsement | None = None,
    scene_entry_endorsement: SceneEntryEndorsement | None = None,
) -> None:
    """Raise ValueError if the source discriminator doesn't match the supplied kwargs."""
    if source == GainSource.POSE_ENDORSEMENT:
        if pose_endorsement is None:
            msg = "POSE_ENDORSEMENT source requires pose_endorsement= kwarg."
            raise ValueError(msg)
        return
    if source == GainSource.SCENE_ENTRY:
        if scene_entry_endorsement is None:
            msg = "SCENE_ENTRY source requires scene_entry_endorsement= kwarg."
            raise ValueError(msg)
        return
    if source == GainSource.OUTFIT_TRICKLE:
        msg = "OUTFIT_TRICKLE source is reserved; item_instance FK ships with Items system."
        raise ValueError(msg)
    if source == GainSource.ROOM_RESIDENCE:
        if room_aura_profile is None:
            msg = "ROOM_RESIDENCE source requires room_aura_profile= kwarg."
            raise ValueError(msg)
        return
    if source == GainSource.STAFF_GRANT:
        # staff_account nullable by design (e.g. retirement can null it)
        return
    msg = f"Unknown GainSource: {source!r}"
    raise ValueError(msg)


@transaction.atomic
def spend_resonance_for_imbuing(  # noqa: C901 — sequential guards + greedy loop, complexity is inherent
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
    while True:
        n = thread.level
        next_level = n + 1
        cost = max((n - 9) * 100, 1)  # sub-10 levels cost 1 dp each
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
_ALWAYS_IN_ACTION_KINDS = frozenset(
    {TargetKind.RELATIONSHIP_TRACK, TargetKind.RELATIONSHIP_CAPSTONE}
)


def _anchor_in_action(thread: Thread, ctx: PullActionContext) -> bool:
    """Return True iff ``thread``'s anchor is involved in the action (Spec A §5.2).

    Relationship anchors are always considered in-action (player asserts
    involvement). Other kinds are matched against the explicit ``involved_*``
    tuples on the context — the caller is responsible for populating those.
    """
    if thread.target_kind in _ALWAYS_IN_ACTION_KINDS:
        return True
    if thread.target_kind == TargetKind.TRAIT:
        return thread.target_trait_id in ctx.involved_traits
    if thread.target_kind == TargetKind.TECHNIQUE:
        return thread.target_technique_id in ctx.involved_techniques
    if thread.target_kind in (TargetKind.ITEM, TargetKind.ROOM):
        return thread.target_object_id in ctx.involved_objects
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
            rows = ThreadPullEffect.objects.filter(
                target_kind=t.target_kind,
                resonance=t.resonance,
                tier=effect_tier,
                min_thread_level__lte=t.level,
            )
            for row in rows:
                authored = (
                    row.flat_bonus_amount or row.intensity_bump_amount or row.vital_bonus_amount
                )
                # CAPABILITY_GRANT and NARRATIVE_ONLY have no numeric payload;
                # their scaled_value must be None (DB CheckConstraint forbids 0).
                has_numeric_payload = row.effect_kind not in (
                    EffectKind.CAPABILITY_GRANT,
                    EffectKind.NARRATIVE_ONLY,
                )
                base_scaled: int | None = (
                    (authored or 0) * multiplier if has_numeric_payload else None
                )
                inactive = row.effect_kind == EffectKind.VITAL_BONUS and not in_combat
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
                    )
                )
    return resolved


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

    cost = ThreadPullCost.objects.get(tier=tier)
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
    assert encounter is not None  # noqa: S101 — caller branched on this
    assert participant is not None  # noqa: S101 — paired with encounter
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
        )


@transaction.atomic
def spend_resonance_for_pull(  # noqa: C901 — sequential guards + combat/ephemeral branches, complexity is inherent
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

    cost = ThreadPullCost.objects.get(tier=tier)
    n_threads = len(threads)

    for t in threads:
        if t.owner_id != character_sheet.pk:
            msg = "Thread not owned by character."
            raise InvalidImbueAmount(msg)
        if t.resonance_id != resonance.pk:
            msg = "Thread does not share the chosen resonance."
            raise InvalidImbueAmount(msg)
        if not _anchor_in_action(t, action_context):
            msg = "Thread anchor is not involved in this action."
            raise InvalidImbueAmount(msg)

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
