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

from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import (
    ANCHOR_CAP_COVENANT_DAYS_DIVISOR,
    ANCHOR_CAP_COVENANT_LEGEND_DIVISOR,
    ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER,
    ANCHOR_CAP_FACET_DIVISOR,
    ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE,
    ANCHOR_CAP_GIFT_PER_STAGE,
    TargetKind,
    VitalBonusTarget,
)
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    MantleNotClearedError,
    RelationshipBondNotOwned,
    WeavingUnlockMissing,
    XPInsufficient,
)
from world.magic.models import (
    CharacterResonance,
    CharacterThreadWeavingUnlock,
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadXPLockedLevel,
)
from world.magic.types import ThreadSurvivabilitySaves, ThreadXPLockProspect

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import DamageType
    from world.magic.models import (
        Resonance as ResonanceModel,
        ThreadWeavingTeachingOffer,
        ThreadWeavingUnlock,
    )
    from world.magic.models.gifts import Gift

logger = logging.getLogger(__name__)


def thread_level_multiplier(level: int) -> Decimal:
    """The shared level-bucketing multiplier for thread-pull-effect scaling (#1718).

    A freshly-provisioned thread (level 0) keeps today's floor of 1 — several
    consumers (e.g. _gift_thread_depth) document this as a deliberate
    guarantee for newly-provisioned threads, not part of the continuous
    investment curve. For level 1-9, a linear ramp from 0.1 (level 1) to 1.0
    (level 10) replaces the old flat floor of 1 for all of 1-9 — this is what
    #1718 asked for (a grant of 1 and a grant of 9 no longer feel identical),
    at the cost of levels 1-9 now scoring BELOW today's flat-1 floor rather
    than at or above it. That tradeoff is deliberate: the alternative (ramping
    above 1.0 and clipping back down at the level-10 anchor) creates a worse
    regression — level 9 would outscore level 10, which is a real gameplay
    regression at the exact milestone this feature should improve, and was
    caught in review. Level >= 10 is untouched: max(1, level // 10) exactly.
    """
    if level <= 0:
        return Decimal(1)
    if level >= 10:  # noqa: PLR2004 — the existing 10-per-tier thread-level scale
        return Decimal(level // 10)
    return Decimal(level) / Decimal(10)


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


def _bound_covenant_role_cap_by_court_grant(
    thread: Thread,
    base_cap: int,
    covenant_ids: list[int],
) -> int:
    """Bound a COVENANT_ROLE thread's anchor cap by the master's granted cap (#1589 Task 6).

    Durance/Battle roles return ``base_cap`` byte-for-byte unchanged. For a COURT
    role the cap is additionally bounded by what the servant's master granted them
    (``CourtPact.granted_pull_cap``): ONE query, reusing the already-warmed
    ``covenant_ids`` — no per-covenant loop.

    Semantics: a Court servant with NO active pact (master granted nothing) →
    ``granted = 0`` → cap ``0`` → they cannot pull their Court-role thread. This is
    intended; the grant is the gate.
    """
    from world.covenants.constants import CovenantType  # noqa: PLC0415

    if thread.target_covenant_role.covenant_type != CovenantType.COURT:
        return base_cap

    from world.covenants.models import CourtPact  # noqa: PLC0415

    granted = (
        CourtPact.objects.filter(
            covenant_id__in=covenant_ids,
            servant_sheet=thread.owner,
            released_at__isnull=True,
        )
        .order_by("-granted_pull_cap")
        .values_list("granted_pull_cap", flat=True)
        .first()
    )
    return min(base_cap, granted if granted is not None else 0)


def compute_anchor_cap(thread: Thread) -> int:  # noqa: PLR0911, C901
    """Return the anchor-side cap for this thread (Spec A §2.4).

    Rules per target_kind:
    - TRAIT: CharacterTraitValue.value for (owner's ObjectDB, target_trait).
      CharacterTraitValue.character is a FK to ObjectDB, so we navigate
      thread.owner.character (CharacterSheet → ObjectDB) for the lookup.
    - TECHNIQUE: target_technique.level × 10
    - RELATIONSHIP_TRACK: target_relationship_track.developed_points.
      target_relationship_track is a FK to RelationshipTrackProgress;
      developed_points reflects the relationship's accumulated permanent
      depth on this track. anchor_cap grows continuously with relationship
      depth (every point matters, not just tier thresholds).
    - RELATIONSHIP_CAPSTONE: target_capstone.points. The capstone's own
      points value (set at authoring time by the relationship system) is
      the anchor cap. path_cap remains the absolute ceiling on Thread.level.
    - FACET: min(lifetime_earned // ANCHOR_CAP_FACET_DIVISOR,
      path_stage × ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE).
    - COVENANT_ROLE: max_covenant_level × ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER (covenant
      component) + legend_earned_in_role // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR (personal
      deeds) + days_held_in_role // ANCHOR_CAP_COVENANT_DAYS_DIVISOR (personal tenure).
      Use-based (issue #517): personal investment adds on top of the covenant floor.
    - MANTLE: max cleared mantle level × 10 (Spec D §6.2). Cap grows as the
      character clears higher mantle ranks via codex research.
    - SANCTUM: target_sanctum_details.feature_instance.level × 10 (Plan 4 §F).
      Cap scales with the Sanctum's upgrade level (1–5 → 10–50).
    - GIFT: current_path_stage × ANCHOR_CAP_GIFT_PER_STAGE (#1580). Species gift
      threads grow in lockstep with the character's path stage (stage 2 → cap 20).
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
            return int(thread.target_relationship_track.developed_points)
        case TargetKind.RELATIONSHIP_CAPSTONE:
            return int(thread.target_capstone.points)
        case TargetKind.FACET:
            lifetime = thread.owner.character.resonances.lifetime(thread.resonance)
            hard_max = _current_path_stage(thread.owner) * ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE
            return min(lifetime // ANCHOR_CAP_FACET_DIVISOR, hard_max)
        case TargetKind.COVENANT_ROLE:
            from world.societies.services import get_character_role_legend  # noqa: PLC0415

            role = thread.target_covenant_role
            handler = thread.owner.character.covenant_roles
            # covenant_ids come from the warmed handler cache (0 queries); reused by
            # both the legend lookup and the Court-pact bound below.
            covenant_ids = handler.covenant_ids_for_role(role)
            covenant_component = (
                handler.max_covenant_level_for_role(role) * ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER
            )
            # The legend lookup then needs only its own credit query rather than
            # re-fetching membership.
            legend = get_character_role_legend(
                character_sheet=thread.owner,
                role=role,
                covenant_ids=covenant_ids,
            )
            days = handler.days_held_in_role(role)
            base_cap = (
                covenant_component
                + legend // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR
                + days // ANCHOR_CAP_COVENANT_DAYS_DIVISOR
            )
            return _bound_covenant_role_cap_by_court_grant(thread, base_cap, covenant_ids)
        case TargetKind.MANTLE:
            mantle = thread.target_mantle
            max_level = thread.owner.character.mantle_clearances.max_cleared_level(mantle)
            return max_level * 10
        case TargetKind.SANCTUM:
            return thread.target_sanctum_details.feature_instance.level * 10
        case TargetKind.GIFT:
            return _current_path_stage(thread.owner) * ANCHOR_CAP_GIFT_PER_STAGE
        case TargetKind.ORGANIZATION:
            org = thread.target_organization
            handler = org.gift_grants_handler
            grant_cap = handler.anchor_cap_for(thread.resonance)
            path_cap = _current_path_stage(thread.owner) * ANCHOR_CAP_GIFT_PER_STAGE
            return min(grant_cap, path_cap)
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
# Resonance Pivot Spec A — per-target-kind IMBUE premium (ADR-0051); pull cost is uniform
# =============================================================================


def get_pull_cost(tier: int, target_kind: str | None) -> ThreadPullCost:
    """Resolve the pull cost row for (tier, target_kind).

    Prefers a kind-specific row (``target_kind`` set); falls back to the
    universal default row (``target_kind=None``). Mirrors the
    ``get_pull_effects_for_thread`` gift-specific-then-null fallback pattern.

    ``target_kind`` is normalized through ``TargetKind(value)`` when not None
    to fail fast on garbage input rather than silently falling back.

    Args:
        tier: Pull intensity tier (1, 2, or 3).
        target_kind: A ``TargetKind`` value, or None for the universal default.

    Returns:
        The matching ``ThreadPullCost`` row.

    Raises:
        ValueError: If ``target_kind`` is not a valid ``TargetKind`` value.
        ThreadPullCost.DoesNotExist: If no universal row exists for ``tier``.
    """
    if target_kind is not None:
        TargetKind(target_kind)  # validate; raises ValueError on bad input
        specific = ThreadPullCost.objects.filter(tier=tier, target_kind=target_kind).first()
        if specific is not None:
            return specific
    return ThreadPullCost.objects.get(tier=tier, target_kind__isnull=True)


def get_imbue_cost_multiplier(target_kind: str | None) -> int:
    """Resolve the imbue dp cost multiplier for a thread kind (ADR-0051).

    Reads the multiplier from the tier-1 cost row for ``target_kind`` (or the
    universal row). Defaults to 1 when no row is found. This keeps all tuning
    in the ``ThreadPullCost`` data surface rather than a module constant.

    Args:
        target_kind: A ``TargetKind`` value, or None for the universal default.

    Returns:
        The imbue cost multiplier (default 1).
    """
    try:
        return get_pull_cost(1, target_kind).imbue_cost_multiplier
    except ThreadPullCost.DoesNotExist:
        return 1


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

    from world.magic.services.alterations import enforce_advancement_gate  # noqa: PLC0415

    enforce_advancement_gate(character_sheet)

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


def _weave_gift_thread(
    character_sheet: CharacterSheet,
    gift: Gift,
    resonance: ResonanceModel,
    *,
    name: str = "",
    description: str = "",
) -> Thread:
    """GIFT weave: commit/choose a resonance onto a latent GIFT thread.

    With multi-resonance (#1619), a character may hold multiple GIFT threads
    on the same gift at different resonances. Weaving finds the thread at the
    specified resonance (or provisions one if none exists at that resonance).
    It does NOT change the resonance of an existing thread at a different
    resonance — each resonance gets its own thread.
    """
    # Resonance-in-supported-set check: read the gift's cached resonance list
    # (list-comp) rather than ``gift.resonances.filter(pk=…).exists()`` per
    # project cached-property rule.
    if not any(r.pk == resonance.pk for r in gift.cached_resonances):
        from world.magic.exceptions import UnsupportedGiftResonanceError  # noqa: PLC0415

        raise UnsupportedGiftResonanceError

    # Read the existing threads through the cached ``character.threads``
    # handler (same cached queryset the resolver reads), not a fresh
    # ``Thread.objects.filter()``. The handler's list is already filtered to
    # retired_at__isnull=True.
    character = character_sheet.character
    # #1619: Look for a thread at the specified resonance first.
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT
            and t.target_gift_id == gift.pk
            and t.resonance_id == resonance.pk
        ),
        None,
    )
    if thread is None:
        # No thread at this resonance yet: provision one (idempotent).
        from world.magic.specialization.services import (  # noqa: PLC0415
            provision_latent_gift_thread,
        )

        return provision_latent_gift_thread(character_sheet, gift, resonance=resonance)

    if name:
        thread.name = name
    if description:
        thread.description = description
    if name or description:
        thread.save(update_fields=["name", "description"])
    return thread


def _satisfy_thread_woven(character_sheet: CharacterSheet) -> None:
    """Fire the THREAD_WOVEN external-act beat for ``weave_thread`` (#1035).

    Cheap-guarded, failure-isolated via ``notify_external_act`` (ADR-0112) — isolation
    from the caller's own ``@transaction.atomic`` block now lives in that shared wrapper.
    Shared by both ``weave_thread`` exit points (the GIFT early-return and the general
    tail) so a successful GIFT weave fires the beat too.
    """
    from world.missions.constants import ExternalAct  # noqa: PLC0415
    from world.missions.services.external_acts import notify_external_act  # noqa: PLC0415

    notify_external_act(character_sheet, ExternalAct.THREAD_WOVEN)


@transaction.atomic
def _has_weaving_unlock(
    character_sheet: CharacterSheet,
    target_kind: str,
    target: object,
) -> bool:
    """Check if a character has the required ThreadWeavingUnlock for a given anchor.

    Spec A §7.4 eligibility table (lines 449-457). Delegates to the cached
    CharacterWeavingUnlockHandler (ADR-0093) — no .filter()/.exists() queries.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    handler = character_sheet.character.weaving_unlocks
    match target_kind:
        case TargetKind.TRAIT:
            return handler.has_unlock_for_trait(target)
        case TargetKind.TECHNIQUE:
            return handler.has_unlock_for_gift(target.gift)  # type: ignore[union-attr]
        case TargetKind.RELATIONSHIP_TRACK | TargetKind.RELATIONSHIP_CAPSTONE:
            # Both RelationshipTrackProgress and RelationshipCapstone expose .track
            track = target.track  # type: ignore[union-attr]
            return handler.has_unlock_for_track(track)
        # Kind-level unlocks: any unlock of that target_kind suffices.
        case TargetKind.FACET | TargetKind.SANCTUM | TargetKind.ORGANIZATION:
            return handler.has_unlock_for_kind(target_kind)
    return False


def _validate_covenant_role_anchor(
    character_sheet: CharacterSheet,
    target: object,
) -> None:
    """Raise ``CovenantRoleNeverHeldError`` when the character never held the role."""
    from world.covenants.exceptions import CovenantRoleNeverHeldError  # noqa: PLC0415

    if not character_sheet.character.covenant_roles.has_ever_held(target):
        raise CovenantRoleNeverHeldError


def _validate_mantle_anchor(
    character_sheet: CharacterSheet,
    target: object,
) -> None:
    """Record mantle clearances and raise ``MantleNotClearedError`` if uncleared."""
    from world.items.services.mantle import (  # noqa: PLC0415
        get_max_cleared_mantle_level,
        record_mantle_clearances,
    )

    record_mantle_clearances(character_sheet, target)  # type: ignore[invalid-argument-type]
    if get_max_cleared_mantle_level(character_sheet, target) < 1:  # type: ignore[invalid-argument-type]
        raise MantleNotClearedError


def _validate_organization_anchor(
    character_sheet: CharacterSheet,
    target: object,
) -> None:
    """Validate org membership + kind-level weaving unlock for ORGANIZATION threads."""
    from world.magic.constants import TargetKind  # noqa: PLC0415

    # Gate 1: active membership — the character's persona must be an active
    # member of the target org. Read through the persona's membership list.
    persona = character_sheet.primary_persona
    if persona is None:
        msg = "Character has no primary persona; cannot verify org membership."
        raise WeavingUnlockMissing(msg)
    memberships = list(persona.organization_memberships.all())
    is_member = any(
        m.organization_id == target.pk  # type: ignore[union-attr]
        and m.left_at is None
        and m.exiled_at is None
        for m in memberships
    )
    if not is_member:
        msg = "Character is not an active member of this organization."
        raise WeavingUnlockMissing(msg)
    # Gate 2: kind-level weaving unlock.
    if not character_sheet.character.weaving_unlocks.has_unlock_for_kind(TargetKind.ORGANIZATION):
        msg = "Character lacks the ORGANIZATION weaving unlock."
        raise WeavingUnlockMissing(msg)


def _validate_relationship_ownership(
    character_sheet: CharacterSheet,
    target: object,
) -> None:
    """Raise ``RelationshipBondNotOwned`` when the target's relationship is foreign.

    Both RelationshipTrackProgress and RelationshipCapstone expose
    ``.relationship``; only the relationship's own source may weave a thread
    on it. Checked AFTER the unlock gate (#2033 adversarial review): defense-
    in-depth for direct service callers — the API and telnet resolvers are
    already scoped, so neither can reach this branch with a foreign row.
    Ordering it after the unlock check means an unlocked-but-unauthorized
    caller sees WeavingUnlockMissing first, never learning whether the
    foreign row even exists.
    """
    if target.relationship.source_id != character_sheet.pk:  # type: ignore[union-attr]
        raise RelationshipBondNotOwned


def _validate_technique_ownership(
    character_sheet: CharacterSheet,
    target: object,
) -> None:
    """Raise ``TechniqueNotOwned`` when the character doesn't know the technique (#1582)."""
    from world.magic.exceptions import TechniqueNotOwned  # noqa: PLC0415
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    if not CharacterTechnique.objects.filter(character=character_sheet, technique=target).exists():
        raise TechniqueNotOwned


def _validate_anchor(
    character_sheet: CharacterSheet,
    target_kind: str,
    target: object,
) -> None:
    """Dispatch anchor-specific validation before thread creation.

    COVENANT_ROLE, MANTLE, and ORGANIZATION have bespoke validation; all other
    kinds fall through to the generic ``_has_weaving_unlock`` gate.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if target_kind == TargetKind.COVENANT_ROLE:
        _validate_covenant_role_anchor(character_sheet, target)
    elif target_kind == TargetKind.MANTLE:
        _validate_mantle_anchor(character_sheet, target)
    elif target_kind == TargetKind.ORGANIZATION:
        _validate_organization_anchor(character_sheet, target)
    elif not _has_weaving_unlock(character_sheet, target_kind, target):
        msg = "Character lacks the required ThreadWeavingUnlock for this anchor."
        raise WeavingUnlockMissing(msg)


@transaction.atomic
def weave_thread(  # noqa: PLR0913
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
        target: The anchor object (Trait, Technique, RelationshipTrackProgress,
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
        RelationshipBondNotOwned: If target_kind is RELATIONSHIP_TRACK or
                RELATIONSHIP_CAPSTONE and the target's relationship is not the
                weaving character's own (relationship.source != character_sheet).
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if target_kind == TargetKind.GIFT:
        thread = _weave_gift_thread(
            character_sheet, target, resonance, name=name, description=description
        )
        _satisfy_thread_woven(character_sheet)
        return thread

    _validate_anchor(character_sheet, target_kind, target)

    if target_kind in (TargetKind.RELATIONSHIP_TRACK, TargetKind.RELATIONSHIP_CAPSTONE):
        _validate_relationship_ownership(character_sheet, target)

    # A signature (TECHNIQUE) thread requires that the character actually knows
    # the technique being signed (#1582).
    if target_kind == TargetKind.TECHNIQUE:
        _validate_technique_ownership(character_sheet, target)

    field_map: dict[str, str] = {
        TargetKind.TRAIT: "target_trait",
        TargetKind.TECHNIQUE: "target_technique",
        TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
        TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
        TargetKind.FACET: "target_facet",
        TargetKind.COVENANT_ROLE: "target_covenant_role",
        TargetKind.MANTLE: "target_mantle",
        TargetKind.ORGANIZATION: "target_organization",
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
    thread = Thread.objects.create(**kwargs)
    recompute_max_health_with_threads(character_sheet)
    character_sheet.character.threads.invalidate()

    # For ORGANIZATION threads, mint CharacterTechnique rows for the org's
    # acquired gifts whose supported-resonance set contains the thread's chosen
    # resonance. Idempotent — existing technique ownership is skipped.
    if target_kind == TargetKind.ORGANIZATION:
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        org = target  # type: ignore[assignment]
        handler = org.gift_grants_handler
        techniques = handler.acquired_techniques_for(resonance)
        for technique in techniques:
            CharacterTechnique.objects.get_or_create(character=character_sheet, technique=technique)

    _satisfy_thread_woven(character_sheet)

    return thread


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

# TODO(perf): The three prospect helpers below each fire a Thread.objects.filter(owner=...)
# query; ThreadHubSummaryView calls all three, so a hub render is 3 thread queries plus
# any per-kind anchor-cap queries (compute_anchor_cap hits CharacterTraitValue,
# current_tier traversal, etc.). Acceptable at low thread counts but worth profiling
# if a character grows past ~20 threads.


def imbue_ready_threads(character_sheet: CharacterSheet) -> list[Thread]:
    """Return threads that have matching CharacterResonance balance > 0 and level < cap.

    Spec A §3.6.
    """
    threads = list(
        Thread.objects.filter(owner=character_sheet, retired_at__isnull=True).select_related(
            "resonance__affinity",
            "target_trait",
            "target_technique",
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


def weaving_eligibility_for(character_sheet: CharacterSheet) -> dict[str, bool]:
    """Return whether the character has at least one weaving unlock per TargetKind.

    Returns a dict keyed by TargetKind values (strings), all False for a character
    with no unlocks. COVENANT_ROLE is special: it requires the character to have
    ever held any covenant role (no authored ThreadWeavingUnlock for this kind).
    """
    unlocks = list(
        CharacterThreadWeavingUnlock.objects.filter(
            character=character_sheet,
        ).select_related("unlock")
    )
    eligibility: dict[str, bool] = {kind.value: False for kind in TargetKind}
    for cu in unlocks:
        eligibility[cu.unlock.target_kind] = True

    # COVENANT_ROLE eligibility: character has ever held any covenant role.
    # The CharacterCovenantRoleHandler is accessed via character.covenant_roles.
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    eligibility[TargetKind.COVENANT_ROLE.value] = CharacterCovenantRole.objects.filter(
        character_sheet=character_sheet
    ).exists()

    return eligibility


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
    from world.magic.services.alterations import enforce_advancement_gate  # noqa: PLC0415

    enforce_advancement_gate(learner)

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

    purchase = CharacterThreadWeavingUnlock.objects.create(
        character=learner,
        unlock=unlock,
        xp_spent=xp_cost,
        teacher=offer.teacher,
    )
    # Invalidate the cached handler so the next read sees the new unlock (ADR-0093).
    learner.character.weaving_unlocks.invalidate()
    return purchase


# =============================================================================
# Phase 14 — Thread survivability tuning (#1175)
# =============================================================================

THREAD_SURVIVABILITY_DEFAULTS: dict[str, tuple[int, int, int]] = {
    # vital_target: (coefficient, cap, half_saturation)
    VitalBonusTarget.DAMAGE_TAKEN_REDUCTION: (1, 20, 8),
    VitalBonusTarget.MAX_HEALTH: (1, 80, 10),
    VitalBonusTarget.DEATH_SAVE: (1, 15, 8),
    VitalBonusTarget.KNOCKOUT_RESIST: (1, 15, 8),
    VitalBonusTarget.PERMANENT_WOUND_RESIST: (1, 15, 8),
}


def seed_thread_survivability_tuning() -> None:
    """Idempotently author the default ThreadSurvivabilityTuning rows (#1175)."""
    from world.magic.models import ThreadSurvivabilityTuning  # noqa: PLC0415

    for target, (coefficient, cap, half) in THREAD_SURVIVABILITY_DEFAULTS.items():
        ThreadSurvivabilityTuning.objects.get_or_create(
            vital_target=target,
            defaults={"coefficient": coefficient, "cap": cap, "half_saturation": half},
        )


def get_thread_survivability_tuning(vital_target: str) -> "ThreadSurvivabilityTuning | None":  # noqa: F821, UP037
    """Return the tuning row for a target, or None if unseeded (baseline 0)."""
    from world.magic.models import ThreadSurvivabilityTuning  # noqa: PLC0415

    return ThreadSurvivabilityTuning.objects.filter(vital_target=vital_target).first()


def _soft_cap(score: Decimal | int, cap: int, half_saturation: int) -> int:
    """round(cap * score / (score + half)) with a 0 floor at score<=0."""
    if score <= 0:
        return 0
    return round(cap * score / (score + half_saturation))


def survivability_baseline(character: ObjectDB, vital_target: str) -> int:
    """Universal soft-capped survivability baseline from thread investment (#1175),
    amplified per-thread by the fashion/motif coherence of each thread's own
    resonance (#1252).

    S = coefficient × Σ depth(t) × coherence_factor(t) over owned (non-retired)
    threads, where depth(t) = thread_level_multiplier(thread.level) (#1718) and
    coherence_factor(t) = min(coherence_max_multiplier, 1 +
    motif_coherence_bonus(sheet, thread.resonance) / coherence_scale). An
    uncoordinated wardrobe yields factor 1.0 (no penalty).
    baseline = round(cap × S / (S + half_saturation)); 0 with no tuning row or
    no threads.
    """
    from world.mechanics.services import motif_coherence_bonus  # noqa: PLC0415

    tuning = get_thread_survivability_tuning(vital_target)
    if tuning is None:
        return 0
    threads = character.threads._all  # noqa: SLF001 — same handler used by passive_vital_bonuses
    sheet = character.sheet_data
    score = Decimal(0)
    coherence_by_resonance: dict[int, int] = {}
    for t in threads:
        depth = thread_level_multiplier(t.level)
        factor = Decimal(1)
        if tuning.coherence_scale:
            if t.resonance_id not in coherence_by_resonance:
                coherence_by_resonance[t.resonance_id] = motif_coherence_bonus(
                    sheet, t.resonance_id
                )
            bonus = coherence_by_resonance[t.resonance_id]
            factor = min(
                Decimal(str(tuning.coherence_max_multiplier)),
                Decimal(1) + Decimal(bonus) / Decimal(tuning.coherence_scale),
            )
        score += Decimal(depth) * factor
    scaled = tuning.coefficient * score
    return _soft_cap(scaled, tuning.cap, tuning.half_saturation)


def total_thread_level_across_all_kinds(sheet: CharacterSheet) -> int:
    """Sum raw ``thread.level`` across ALL of a character's non-retired threads (#2529).

    Formula B for the covenant-role blend baseline: total magical investment
    across every thread kind (TECHNIQUE, GIFT, COVENANT_ROLE, SANCTUM, ...),
    reading the cached ``character.threads`` handler. Raw levels, NOT the
    ``thread_level_multiplier`` bucketing ``survivability_baseline`` uses.
    """
    return sum(thread.level for thread in sheet.character.threads.all())


def survivability_save_baselines(character: ObjectDB) -> ThreadSurvivabilitySaves:
    """Per-tier survivability save modifiers from thread investment (#1250).

    Each is a soft-capped baseline added to the character's rollmod in the
    matching tier of ``process_damage_consequences``. All 0 for a lone wolf.
    """
    return ThreadSurvivabilitySaves(
        wound=survivability_baseline(character, VitalBonusTarget.PERMANENT_WOUND_RESIST),
        death=survivability_baseline(character, VitalBonusTarget.DEATH_SAVE),
        knockout=survivability_baseline(character, VitalBonusTarget.KNOCKOUT_RESIST),
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
    baseline = survivability_baseline(character, VitalBonusTarget.MAX_HEALTH)
    return recompute_max_health(character_sheet, thread_addend=passive + pulled + baseline)


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
    baseline = survivability_baseline(character, VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
    return max(0, incoming_damage - (passive + pulled + baseline))


def gift_thread_resistance(character: ObjectDB, damage_type: DamageType) -> int:
    """Total damage-type-specific resistance from gift threads (#1580).

    Mirrors ``conditions.resistance_modifier(damage_type)``: returns a POSITIVE
    value that is subtracted on the SAME incoming-damage computation in
    ``apply_damage_to_participant`` where the species drawback's negative
    ``ConditionResistanceModifier`` is applied, so the drawback vulnerability and
    the gift resistance net correctly. Combines:

    - passive tier-0 RESISTANCE rows on owned threads (flat ``resistance_amount``,
      gated by ``min_thread_level``); and
    - active paid-pull RESISTANCE snapshots (``scaled_value`` =
      ``resistance_amount × level_multiplier``), stronger at higher thread level.

    This is the damage-type-specific counterpart to
    ``apply_damage_reduction_from_threads`` (which is damage-type-agnostic). It is
    wired only at the combat damage seam — the same seam where the drawback
    vulnerability is read — because that is where the two must net; the DoT/trap
    seams apply neither the condition resistance nor this gift resistance.
    """
    passive = character.threads.passive_damage_type_resistance(damage_type)
    pulled = character.combat_pulls.active_pull_resistance(damage_type)
    return passive + pulled
