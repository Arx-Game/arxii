"""Thread / weaving / cap / pull-routing service functions for the magic system.

Covers:
- Cap & lock math (Spec A §2.4): anchor/path/effective cap helpers
- Typeclass-registry lookup utility (_typeclass_path_in_registry)
- Weaving unlock eligibility + thread creation + narrative update
- Thread imbue/XP-lock-boundary queries for the Imbuing ritual UI
- ThreadWeaving teaching-offer acceptance (Spec A §6.1, §6.2)
- VITAL_BONUS routing (Spec A §3.8, §5.5, §5.8, §7.4): max-health recompute
  and damage-reduction helpers
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import (
    ANCHOR_CAP_FACET_DIVISOR,
    ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE,
    TargetKind,
    VitalBonusTarget,
)
from world.magic.exceptions import (
    AnchorCapExceeded,
    AnchorCapNotImplemented,
    InvalidImbueAmount,
    WeavingUnlockMissing,
    XPInsufficient,
)
from world.magic.models import (
    CharacterResonance,
    CharacterThreadWeavingUnlock,
    Thread,
    ThreadLevelUnlock,
    ThreadXPLockedLevel,
)
from world.magic.types import ThreadXPLockProspect

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import (
        Resonance as ResonanceModel,
        ThreadWeavingTeachingOffer,
        ThreadWeavingUnlock,
    )


def _typeclass_path_in_registry(path: str, registry: tuple[str, ...]) -> bool:
    """Return True iff ``path`` (or any of its MRO base paths) is in ``registry``.

    Honors typeclass inheritance: a registered base typeclass admits all
    subclasses (e.g. registering Sword admits LongSword).

    Empty registry rejects everything — callers explicitly want "no items
    registered" to mean "no items eligible".
    """
    if not registry:
        return False
    if path in registry:
        return True
    from evennia.utils.utils import class_from_module  # noqa: PLC0415

    cls = class_from_module(path)
    for base in cls.__mro__[1:]:
        base_path = f"{base.__module__}.{base.__qualname__}"
        if base_path in registry:
            return True
    return False


# =============================================================================
# Resonance Pivot Spec A — Phase 10: Cap helpers (§2.4)
# =============================================================================


def _current_path_stage(character_sheet: CharacterSheet) -> int:
    """Return the stage of the most-recently-selected Path; 1 if none.

    Navigates CharacterSheet → ObjectDB (character) → path_history (reverse FK
    on CharacterPathHistory), ordered by -selected_at then -pk for deterministic
    tie-breaking. Returns path.stage as int.
    """
    history = (
        character_sheet.character.path_history.select_related("path")
        .order_by("-selected_at", "-pk")
        .first()
    )
    if history is None:
        return 1
    return int(history.path.stage)


def compute_anchor_cap(thread: Thread) -> int:  # noqa: PLR0911 — one arm per TargetKind, hard to collapse further
    """Return the anchor-side cap for this thread (Spec A §2.4).

    Rules per target_kind:
    - TRAIT: CharacterTraitValue.value for (owner's ObjectDB, target_trait).
      CharacterTraitValue.character is a FK to ObjectDB, so we navigate
      thread.owner.character (CharacterSheet → ObjectDB) for the lookup.
    - TECHNIQUE: target_technique.level × 10
    - RELATIONSHIP_TRACK: current tier_number of RelationshipTrackProgress × 10.
      Uses RelationshipTrackProgress.current_tier (property returning the
      highest RelationshipTier whose point_threshold ≤ developed_points);
      defaults to 0 if no tier reached.
    - RELATIONSHIP_CAPSTONE: character's current path stage × 10 (same
      formula as path cap; capstone threads are gated by the mage's growth).
    - FACET: min(lifetime_earned // ANCHOR_CAP_FACET_DIVISOR,
      path_stage × ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE).
    - COVENANT_ROLE: current_level × 10.
    - ROOM: not yet implemented — raises AnchorCapNotImplemented.
    """
    match thread.target_kind:
        case TargetKind.TRAIT:
            value = (
                thread.target_trait.character_values.filter(character=thread.owner.character)
                .values_list("value", flat=True)
                .first()
            )
            return int(value or 0)
        case TargetKind.TECHNIQUE:
            return int(thread.target_technique.level * 10)
        case TargetKind.RELATIONSHIP_TRACK:
            # current_tier returns the highest RelationshipTier unlocked by
            # developed_points, or None if the relationship hasn't reached any
            # tier threshold yet.
            tier = thread.target_relationship_track.current_tier
            tier_number = tier.tier_number if tier is not None else 0
            return int(tier_number * 10)
        case TargetKind.RELATIONSHIP_CAPSTONE:
            stage = _current_path_stage(thread.owner)
            return int(stage * 10)
        case TargetKind.FACET:
            lifetime = thread.owner.character.resonances.lifetime(thread.resonance)
            hard_max = _current_path_stage(thread.owner) * ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE
            return min(lifetime // ANCHOR_CAP_FACET_DIVISOR, hard_max)
        case TargetKind.COVENANT_ROLE:
            return thread.owner.current_level * 10
        case TargetKind.ROOM:
            msg = thread.target_kind + " anchor cap awaits Spec D."
            raise AnchorCapNotImplemented(msg)
    return 0


def compute_path_cap(character_sheet: CharacterSheet) -> int:
    """Return the path-side cap for a character (Spec A §2.4).

    = max(current_path_stage, 1) × 10.  Minimum is 10 so stage-0 characters
    still have a non-zero cap.
    """
    stage = _current_path_stage(character_sheet)
    return max(stage, 1) * 10


def compute_effective_cap(thread: Thread) -> int:
    """Return min(path cap, anchor cap) — the binding limit on this thread (Spec A §2.4)."""
    return min(compute_path_cap(thread.owner), compute_anchor_cap(thread))


# =============================================================================
# XP-lock boundary payment (Phase 11 — Spec A §3.2)
# =============================================================================


@transaction.atomic
def cross_thread_xp_lock(
    character_sheet: CharacterSheet,
    thread: Thread,
    boundary_level: int,
) -> ThreadLevelUnlock:
    """Pay XP to unlock an XP-locked level boundary on a thread.

    Idempotent: if the unlock row already exists, returns it without spending XP.
    Spec A §3.2 lines 774-797.

    Args:
        character_sheet: Character paying XP (must own thread).
        thread: Thread to unlock the boundary on.
        boundary_level: XP-locked boundary level (must exist in ThreadXPLockedLevel).

    Returns:
        ThreadLevelUnlock instance (new or existing).

    Raises:
        InvalidImbueAmount: If ownership fails, boundary <= thread.level, or no price row.
        AnchorCapExceeded: If boundary_level > effective cap.
        XPInsufficient: If the account lacks sufficient XP.
    """
    from world.progression.services.awards import get_or_create_xp_tracker  # noqa: PLC0415

    if thread.owner_id != character_sheet.pk:
        msg = "Character does not own thread."
        raise InvalidImbueAmount(msg)
    if boundary_level <= thread.level:
        msg = "Boundary level must be above thread.level."
        raise InvalidImbueAmount(msg)
    if boundary_level > compute_effective_cap(thread):
        msg = "Boundary level exceeds effective cap."
        raise AnchorCapExceeded(msg)

    locked = ThreadXPLockedLevel.objects.filter(level=boundary_level).first()
    if locked is None:
        msg = "No XP lock defined for this boundary level."
        raise InvalidImbueAmount(msg)

    # Idempotency: if unlock row already exists, return it (no-op).
    existing = ThreadLevelUnlock.objects.filter(
        thread=thread,
        unlocked_level=boundary_level,
    ).first()
    if existing is not None:
        return existing

    # Spend XP.
    account = character_sheet.character.account
    xp_tracker = get_or_create_xp_tracker(account)
    if xp_tracker.current_available < locked.xp_cost:
        msg = "Need " + str(locked.xp_cost) + " XP, have " + str(xp_tracker.current_available) + "."
        raise XPInsufficient(msg)
    xp_tracker.total_spent += locked.xp_cost
    xp_tracker.save(update_fields=["total_spent"])

    return ThreadLevelUnlock.objects.create(
        thread=thread,
        unlocked_level=boundary_level,
        xp_spent=locked.xp_cost,
    )


# =============================================================================
# Weaving — unlock eligibility + Thread creation
# =============================================================================


def _has_weaving_unlock(
    character_sheet: CharacterSheet,
    target_kind: str,
    target: object,
) -> bool:
    """Check if a character has the required ThreadWeavingUnlock for a given anchor.

    Spec A §7.4 eligibility table (lines 449-457).
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    base = CharacterThreadWeavingUnlock.objects.filter(character=character_sheet)
    match target_kind:
        case TargetKind.TRAIT:
            return base.filter(unlock__unlock_trait=target).exists()
        case TargetKind.TECHNIQUE:
            return base.filter(unlock__unlock_gift=target.gift).exists()  # type: ignore[union-attr]
        case TargetKind.ROOM:
            # Match if the unlock's room property is one of the anchor's properties.
            return base.filter(
                unlock__unlock_room_property__in=target.properties.all(),  # type: ignore[union-attr]
            ).exists()
        case TargetKind.RELATIONSHIP_TRACK | TargetKind.RELATIONSHIP_CAPSTONE:
            # Both RelationshipTrackProgress and RelationshipCapstone expose .track
            track = target.track  # type: ignore[union-attr]  # noqa: GETATTR_LITERAL — both relationship anchor types expose .track
            return base.filter(unlock__unlock_track=track).exists()
        case TargetKind.FACET:
            # Single global FACET unlock — no per-facet variant; any FACET-kind unlock suffices.
            return base.filter(unlock__target_kind=TargetKind.FACET).exists()
    return False


@transaction.atomic
def weave_thread(  # noqa: PLR0913 — kw-only args; target+resonance+kind are distinct, cannot collapse
    character_sheet: CharacterSheet,
    target_kind: str,
    target: object,
    resonance: ResonanceModel,
    *,
    name: str = "",
    description: str = "",
) -> Thread:
    """Create a new Thread anchored to the given target.

    Spec A §7.4. Validates eligibility via CharacterThreadWeavingUnlock before
    creating the Thread.

    Args:
        character_sheet: Character creating the thread.
        target_kind: TargetKind discriminator string.
        target: The anchor object (Trait, Technique, ObjectDB, RelationshipTrackProgress,
                RelationshipCapstone, Facet, CovenantRole).
        resonance: Resonance this thread channels.
        name: Optional narrative name.
        description: Optional narrative description.

    Returns:
        Newly created Thread instance.

    Raises:
        WeavingUnlockMissing: If the character lacks the required weaving unlock.
        CovenantRoleNeverHeldError: If target_kind is COVENANT_ROLE and the
                character has never held the role.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if target_kind == TargetKind.COVENANT_ROLE:
        from world.covenants.exceptions import CovenantRoleNeverHeldError  # noqa: PLC0415

        if not character_sheet.character.covenant_roles.has_ever_held(target):
            raise CovenantRoleNeverHeldError
    elif not _has_weaving_unlock(character_sheet, target_kind, target):
        msg = "Character lacks the required ThreadWeavingUnlock for this anchor."
        raise WeavingUnlockMissing(msg)

    field_map: dict[str, str] = {
        TargetKind.TRAIT: "target_trait",
        TargetKind.TECHNIQUE: "target_technique",
        TargetKind.ROOM: "target_object",
        TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
        TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
        TargetKind.FACET: "target_facet",
        TargetKind.COVENANT_ROLE: "target_covenant_role",
    }
    kwargs: dict[str, object] = {
        "owner": character_sheet,
        "resonance": resonance,
        "target_kind": target_kind,
        "name": name,
        "description": description,
        "level": 0,
        "developed_points": 0,
    }
    kwargs[field_map[target_kind]] = target
    return Thread.objects.create(**kwargs)


def update_thread_narrative(
    thread: Thread,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Thread:
    """Update the narrative name and/or description of a thread.

    Only provided fields are updated. Spec A §3.6.

    Args:
        thread: Thread to update.
        name: New name (omit to leave unchanged).
        description: New description (omit to leave unchanged).

    Returns:
        The updated Thread instance.
    """
    if name is not None:
        thread.name = name
    if description is not None:
        thread.description = description
    thread.save(update_fields=["name", "description", "updated_at"])
    return thread


# =============================================================================
# Imbuing-ritual UI queries (Spec A §3.6)
# =============================================================================


def imbue_ready_threads(character_sheet: CharacterSheet) -> list[Thread]:
    """Return threads that have matching CharacterResonance balance > 0 and level < cap.

    Spec A §3.6.
    """
    threads = list(
        Thread.objects.filter(owner=character_sheet, retired_at__isnull=True).select_related(
            "resonance__affinity",
            "target_trait",
            "target_technique",
            "target_object",
            "target_relationship_track",
            "target_capstone",
        )
    )
    crs = {
        cr.resonance_id: cr
        for cr in CharacterResonance.objects.filter(character_sheet=character_sheet)
    }
    path_cap = compute_path_cap(character_sheet)
    out: list[Thread] = []
    for t in threads:
        cr = crs.get(t.resonance_id)
        if cr is None or cr.balance <= 0:
            continue
        effective_cap = min(path_cap, compute_anchor_cap(t))
        if t.level < effective_cap:
            out.append(t)
    return out


def near_xp_lock_threads(
    character_sheet: CharacterSheet,
    within: int = 100,
) -> list[ThreadXPLockProspect]:
    """Return threads whose dev_points are within `within` of the next XP-locked boundary.

    Only boundaries that aren't already unlocked are included. Spec A §3.6.
    """
    threads = list(Thread.objects.filter(owner=character_sheet, retired_at__isnull=True))
    if not threads:
        return []
    next_boundaries = {((t.level // 10) + 1) * 10 for t in threads}
    locked_map = {
        locked.level: locked
        for locked in ThreadXPLockedLevel.objects.filter(level__in=next_boundaries)
    }
    unlocked_pairs = set(
        ThreadLevelUnlock.objects.filter(
            thread__in=threads, unlocked_level__in=next_boundaries
        ).values_list("thread_id", "unlocked_level")
    )
    out: list[ThreadXPLockProspect] = []
    for t in threads:
        next_boundary = ((t.level // 10) + 1) * 10
        locked = locked_map.get(next_boundary)
        if locked is None:
            continue
        if (t.pk, next_boundary) in unlocked_pairs:
            continue
        dp_needed = sum(max((n - 9) * 100, 1) for n in range(t.level, next_boundary))
        dp_to_boundary = dp_needed - t.developed_points
        if dp_to_boundary <= within:
            out.append(
                ThreadXPLockProspect(
                    thread=t,
                    boundary_level=next_boundary,
                    xp_cost=locked.xp_cost,
                    dev_points_to_boundary=max(dp_to_boundary, 0),
                )
            )
    return out


def threads_blocked_by_cap(character_sheet: CharacterSheet) -> list[Thread]:
    """Return threads that are at their effective cap (no further imbuing helps).

    Spec A §3.6.
    """
    threads = list(Thread.objects.filter(owner=character_sheet, retired_at__isnull=True))
    path_cap = compute_path_cap(character_sheet)
    return [t for t in threads if t.level >= min(path_cap, compute_anchor_cap(t))]


# =============================================================================
# ThreadWeaving teaching-offer acceptance (Spec A §6.1, §6.2)
# =============================================================================


def compute_thread_weaving_xp_cost(
    unlock: ThreadWeavingUnlock,
    learner: CharacterSheet,
) -> int:
    """Compute the XP cost for a learner to acquire a ThreadWeavingUnlock (Spec A §6.2).

    Returns ``unlock.xp_cost`` for Path-neutral unlocks (no paths M2M set) and
    for learners whose path history intersects the unlock's paths.  Returns
    ``int(unlock.xp_cost * unlock.out_of_path_multiplier)`` for learners who
    have never walked any of the unlock's paths.
    """
    unlock_paths = set(unlock.paths.all())
    if not unlock_paths:
        return unlock.xp_cost  # Path-neutral

    learner_paths = {h.path for h in learner.character.path_history.select_related("path")}
    if learner_paths & unlock_paths:
        return unlock.xp_cost  # in-Path

    return int(unlock.xp_cost * unlock.out_of_path_multiplier)  # out-of-Path


@transaction.atomic
def accept_thread_weaving_unlock(
    learner: CharacterSheet,
    offer: ThreadWeavingTeachingOffer,
) -> CharacterThreadWeavingUnlock:
    """Accept a ThreadWeavingTeachingOffer on behalf of a learner (Spec A §6.1).

    Mirrors ``CodexTeachingOffer.accept`` but implemented as a module-level
    service function (Spec A §3.6).  Steps (in order inside the atomic txn):

    1. Compute XP cost via ``compute_thread_weaving_xp_cost``.
    2. Verify learner has enough XP; raise ``XPInsufficient`` if not.
    3. Deduct learner XP and record an ``XPTransaction``.
    4. Consume teacher's banked AP.
    5. Create and return the ``CharacterThreadWeavingUnlock`` row.

    Gold transfer is TODO (matching codex's deferred economy TODO).
    Learner AP is NOT spent — ``ThreadWeavingUnlock`` has no ``learn_cost``
    field, unlike ``CodexEntry``.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.progression.models import XPTransaction  # noqa: PLC0415
    from world.progression.services.awards import get_or_create_xp_tracker  # noqa: PLC0415
    from world.progression.types import ProgressionReason  # noqa: PLC0415

    unlock = offer.unlock
    xp_cost = compute_thread_weaving_xp_cost(unlock, learner)

    account = learner.character.account
    if account is None:
        msg = "Learner character has no linked account; cannot spend XP."
        raise XPInsufficient(msg)

    xp_tracker = get_or_create_xp_tracker(account)
    if not xp_tracker.can_spend(xp_cost):
        msg = f"Need {xp_cost} XP to learn {unlock}, have {xp_tracker.current_available}."
        raise XPInsufficient(msg)

    # Spend the XP (updates total_spent; save is called inside spend_xp).
    xp_tracker.spend_xp(xp_cost)

    XPTransaction.objects.create(
        account=account,
        amount=-xp_cost,
        reason=ProgressionReason.XP_PURCHASE,
        description=f"ThreadWeaving unlock: {unlock}",
        character=learner.character,
        gm=None,
    )

    # Consume teacher's banked AP commitment.
    teacher_pool = ActionPointPool.get_or_create_for_character(offer.teacher.character)
    teacher_pool.consume_banked(offer.banked_ap)

    # TODO: Transfer gold when economy system exists (matching codex TODO).

    return CharacterThreadWeavingUnlock.objects.create(
        character=learner,
        unlock=unlock,
        xp_spent=xp_cost,
        teacher=offer.teacher,
    )


# =============================================================================
# Phase 13 — VITAL_BONUS routing (Spec A §3.8, §5.5, §5.8, §7.4)
# =============================================================================


def recompute_max_health_with_threads(character_sheet: CharacterSheet) -> int:
    """Recompute max_health folding in thread-derived VITAL_BONUS addends.

    Spec A §5.8 lines 1644–1657 + §7.4 lines 2011–2024. Sums two
    contribution sources and delegates to ``vitals.recompute_max_health``:

    - passive tier-0 VITAL_BONUS rows on every owned thread
      (via ``character.threads.passive_vital_bonuses(MAX_HEALTH)``)
    - active-pull tier 1+ contributions from any live ``CombatPull``
      (via ``character.combat_pulls.active_pull_vital_bonuses(MAX_HEALTH)``)

    Clamp-not-injure semantics (§3.8) live in ``recompute_max_health`` itself:
    when a pull expires and this is called from ``expire_pulls_for_round``,
    the new max may drop below the character's current health. Current is
    clamped to the new max — it never gets *pushed below* its existing
    value, so pull expiry cannot retroactively injure.

    Returns the new max_health value.
    """
    from world.vitals.services import recompute_max_health  # noqa: PLC0415

    character = character_sheet.character
    passive = character.threads.passive_vital_bonuses(VitalBonusTarget.MAX_HEALTH)
    pulled = character.combat_pulls.active_pull_vital_bonuses(VitalBonusTarget.MAX_HEALTH)
    return recompute_max_health(character_sheet, thread_addend=passive + pulled)


def apply_damage_reduction_from_threads(
    character: ObjectDB,
    incoming_damage: int,
) -> int:
    """Reduce incoming damage by thread-derived DAMAGE_TAKEN_REDUCTION.

    Spec A §5.8 lines 1658–1668 + §7.4 lines 2025–2030. Reads passive tier-0
    + active-pull tier 1+ DAMAGE_TAKEN_REDUCTION contributions and returns
    ``max(0, incoming_damage - total)``. Called inline from combat's
    damage pipeline (``apply_damage_to_participant``) between
    ``DAMAGE_PRE_APPLY`` event modification and the actual vitals debit.

    We call this directly from the service rather than registering as a
    flow subscriber: the flow/event system in this codebase routes through
    FlowDefinition DB rows and can't invoke arbitrary Python functions as
    subscribers (see Phase 13 Open Item 3). Thread DR is a read-only
    Python computation over per-character handler caches; inlining it is
    both simpler and cheaper than building subscriber infrastructure.
    """
    passive = character.threads.passive_vital_bonuses(VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
    pulled = character.combat_pulls.active_pull_vital_bonuses(
        VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
    )
    return max(0, incoming_damage - (passive + pulled))
