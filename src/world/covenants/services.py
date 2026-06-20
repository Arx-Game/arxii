"""Service functions for the covenants app."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.covenants.exceptions import (
    CannotKickEqualOrHigherRankError,
    CannotKickSelfError,
    CannotTransferToDepartedMemberError,
    CovenantLevelTooLowError,
    CovenantNameConflictError,
    CovenantRiteError,
    CrossCovenantRankError,
    DuplicateFounderError,
    IncompleteRankReorderError,
    InsufficientFoundersError,
    LastManagerRankError,
    NoActiveBattleError,
    NotAuthorizedToInviteError,
    NotAuthorizedToKickError,
    NotAuthorizedToManageRanksError,
    NotEnoughMembersPresentError,
    SubroleParentMismatchError,
    SubroleResonanceMismatchError,
    SubroleThreadLevelInsufficientError,
)
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantRank,
    CovenantRite,
    CovenantRiteInstance,
    CovenantRiteParticipant,
    CovenantRole,
    GearArchetypeCompatibility,
    MentorBond,
    MentorBondConfig,
)
from world.covenants.types import CovenantFounder
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.exceptions import RequiredReferenceMissingError, SessionTargetMissingError

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.combat.models import CombatEncounter
    from world.covenants.models import CharacterCovenantRole as _CharacterCovenantRole
    from world.magic.models.sessions import RitualSession
    from world.stories.models import Story

MINIMUM_FOUNDERS = 2
_COVENANT_NAME_UNIQUE_MARKER = "name"  # substring in DB integrity error for name uniqueness


def _invalidate_role_caches(character_sheet: CharacterSheet) -> None:
    """Bust the character's thread-handler grant cache after an engagement change.

    ``CharacterThreadHandler.passive_capability_grants()`` (#751) caches the
    engaged-role-gated CAPABILITY_GRANT set on the long-lived, idmapper-cached
    Character typeclass instance. Engaging/disengaging a covenant role changes
    that set, so the handler must be invalidated or role powers go stale.

    Resolves the character via the same ``character_sheet.character`` reverse
    relation the sibling ``.covenant_roles.invalidate()`` calls use throughout
    this module — an engaged membership always has a resolved typeclass.
    """
    character_sheet.character.threads.invalidate()


def _build_default_ladder(covenant: Covenant, *, flat: bool) -> tuple[CovenantRank, CovenantRank]:
    """Create the default rank ladder for a newly formed covenant.

    Default (not flat): two tiers —
      - tier 1 "Founder" (all capability flags True)
      - tier 2 "Member"  (all capability flags False)
    Returns (top_rank, base_rank).

    Flat: one tier —
      - tier 1 "Member" (all capability flags False)
    Returns (member_rank, member_rank) — both slots point to the single rank.
    """
    from world.covenants.constants import (  # noqa: PLC0415
        DEFAULT_FOUNDER_RANK_NAME,
        DEFAULT_MEMBER_RANK_NAME,
    )

    if flat:
        member_rank = CovenantRank.objects.create(
            covenant=covenant,
            name=DEFAULT_MEMBER_RANK_NAME,
            tier=1,
            can_invite=False,
            can_kick=False,
            can_manage_ranks=False,
        )
        return member_rank, member_rank

    founder_rank = CovenantRank.objects.create(
        covenant=covenant,
        name=DEFAULT_FOUNDER_RANK_NAME,
        tier=1,
        can_invite=True,
        can_kick=True,
        can_manage_ranks=True,
    )
    member_rank = CovenantRank.objects.create(
        covenant=covenant,
        name=DEFAULT_MEMBER_RANK_NAME,
        tier=2,
        can_invite=False,
        can_kick=False,
        can_manage_ranks=False,
    )
    return founder_rank, member_rank


@transaction.atomic
def create_covenant(  # noqa: PLR0913
    *,
    name: str,
    covenant_type: str,
    sworn_objective: str,
    founders: Sequence[CovenantFounder],
    battle_binding: str = "",
    campaign_story: Story | None = None,
    flat: bool = False,
) -> Covenant:
    """Create a covenant with its initial set of founder memberships. Atomic.

    Covenants are inherently group structures — formation requires at least
    two distinct founders (`feedback_covenants_are_group_only.md`). The
    serializer layer enforces this for user-supplied data; the service
    raises typed exceptions as defensive assertions against programmer
    errors (Insufficient/DuplicateFounderError).

    Rank ladder:
    - Default (flat=False): "Founder" rank (tier 1, all caps) + "Member" rank (tier 2, no caps).
    - Flat (flat=True): single "Member" rank (tier 1, no caps).

    Seating: the founder with ``is_leader=True`` gets the Founder rank; all others get Member.
    If no founder is flagged is_leader and flat=False, the FIRST founder defaults to leader.
    """
    if len(founders) < MINIMUM_FOUNDERS:
        raise InsufficientFoundersError
    sheet_pks = [founder.character_sheet.pk for founder in founders]
    if len(set(sheet_pks)) != len(sheet_pks):
        raise DuplicateFounderError

    from world.covenants.constants import BattleBinding, CovenantType  # noqa: PLC0415
    from world.covenants.exceptions import (  # noqa: PLC0415
        BattleBindingNotAllowedError,
        BattleBindingRequiredError,
        CampaignStoryNotAllowedError,
    )

    if covenant_type == CovenantType.BATTLE:
        if not battle_binding:
            raise BattleBindingRequiredError
    elif battle_binding:
        raise BattleBindingNotAllowedError

    if campaign_story is not None and battle_binding != BattleBinding.CAMPAIGN:
        raise CampaignStoryNotAllowedError

    cov = Covenant.objects.create(
        name=name,
        covenant_type=covenant_type,
        sworn_objective=sworn_objective,
        battle_binding=battle_binding,
        campaign_story=campaign_story,
    )

    # Build rank ladder and determine which rank each founder gets.
    top_rank, base_rank = _build_default_ladder(cov, flat=flat)

    # Determine the leader: the first is_leader=True founder; if none, the first founder.
    any_leader_flagged = any(f.is_leader for f in founders)
    for idx, founder in enumerate(founders):
        if flat:
            founder_rank = base_rank
        elif founder.is_leader or (not any_leader_flagged and idx == 0):
            founder_rank = top_rank
        else:
            founder_rank = base_rank
        CharacterCovenantRole.objects.create(
            character_sheet=founder.character_sheet,
            covenant=cov,
            covenant_role=founder.role,
            rank=founder_rank,
        )
        founder.character_sheet.character.covenant_roles.invalidate()
    # The covenant is freshly created so its member_roster handler is new, but
    # invalidate for consistency in case the handler was accessed during this flow.
    cov.member_roster.invalidate()
    return cov


def _base_rank(covenant: Covenant) -> CovenantRank:
    """Return the covenant's base rank (highest tier number = lowest authority)."""
    return covenant.ranks.order_by("-tier").first()


def _ensure_base_rank(covenant: Covenant) -> CovenantRank:
    """Return the covenant's base rank, provisioning a default one if it has none.

    Covenants formed via ``create_covenant`` always have a rank ladder. A covenant
    created outside formation (e.g. test/seed factories that instantiate ``Covenant``
    directly) may have no ranks yet, and memberships require a NOT NULL ``rank``. In
    that case, fall back to a single flat "Member" rank (tier 1, no capabilities) —
    matching ``create_covenant``'s flat default — so adding the first member always
    has a valid base rank to assign.
    """
    from world.covenants.constants import DEFAULT_MEMBER_RANK_NAME  # noqa: PLC0415

    base = _base_rank(covenant)
    if base is not None:
        return base
    return CovenantRank.objects.create(
        covenant=covenant,
        name=DEFAULT_MEMBER_RANK_NAME,
        tier=1,
        can_invite=False,
        can_kick=False,
        can_manage_ranks=False,
    )


@transaction.atomic
def add_member(
    *,
    covenant: Covenant,
    character_sheet: CharacterSheet,
    role: CovenantRole,
) -> CharacterCovenantRole:
    """Create a new active membership row. Atomic.

    New members are assigned the covenant's base rank (the rank with the
    highest tier number — lowest authority). The active-uniqueness DB constraint
    enforces "at most one active role per (character, covenant)"; the
    IntegrityError on conflict is the contract.

    Raises VowGateError when the character's level is outside the covenant band
    and they hold no active Mentor's Vow bond in this covenant.
    """
    from world.covenants.mentorship import assert_membership_level_allowed  # noqa: PLC0415

    assert_membership_level_allowed(covenant=covenant, character_sheet=character_sheet)
    rank = _ensure_base_rank(covenant)
    row = CharacterCovenantRole.objects.create(
        character_sheet=character_sheet,
        covenant=covenant,
        covenant_role=role,
        rank=rank,
    )
    character_sheet.character.covenant_roles.invalidate()
    covenant.member_roster.invalidate()
    return row


def can_invite_to_covenant(
    covenant: Covenant,
    *,
    character_sheet: CharacterSheet | None = None,
    account: AccountDB | None = None,
) -> bool:
    """Return True if an active member with a can_invite rank grants invite authority.

    Character-scoped (character_sheet=) for the ritual-draft gate; account-scoped
    (account=) for the CanInviteToCovenant DRF permission. The rank__can_invite +
    active-membership core is shared so the can_invite flag has a single home.
    """
    qs = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        left_at__isnull=True,
        rank__can_invite=True,
    )
    if character_sheet is not None:
        qs = qs.filter(character_sheet=character_sheet)
    if account is not None:
        qs = qs.filter(
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=account,
        )
    return qs.exists()


@transaction.atomic
def change_role(
    *,
    membership: CharacterCovenantRole,
    new_role: CovenantRole,
) -> CharacterCovenantRole:
    """Close the existing membership row; create a new active row in the same covenant.

    Preserves the member's existing rank on the new row.
    """
    existing_rank = membership.rank
    membership.engaged = False
    membership.left_at = timezone.now()
    membership.save(update_fields=["engaged", "left_at"])
    new_row = CharacterCovenantRole.objects.create(
        character_sheet=membership.character_sheet,
        covenant=membership.covenant,
        covenant_role=new_role,
        rank=existing_rank,
    )
    membership.character_sheet.character.covenant_roles.invalidate()
    _invalidate_role_caches(membership.character_sheet)
    membership.covenant.member_roster.invalidate()
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(membership.character_sheet)
    return new_row


@transaction.atomic
def dissolve_covenant(*, covenant: Covenant) -> None:
    """End all active memberships of the covenant; mark covenant dissolved.

    Idempotent: calling on an already-dissolved covenant is a no-op (active
    memberships have already been ended by the prior call).
    """
    if covenant.dissolved_at is not None:
        return
    affected_sheet_ids: set[int] = set()
    active_memberships = list(
        covenant.memberships.filter(left_at__isnull=True).select_related("character_sheet")
    )
    for membership in active_memberships:
        membership.engaged = False
        membership.left_at = timezone.now()
        membership.save(update_fields=["engaged", "left_at"])
        affected_sheet_ids.add(membership.character_sheet_id)
    covenant.dissolved_at = timezone.now()
    covenant.save(update_fields=["dissolved_at"])
    for sheet_id in affected_sheet_ids:
        sheet = CharacterSheet.objects.get(pk=sheet_id)
        sheet.character.covenant_roles.invalidate()
        _invalidate_role_caches(sheet)
    covenant.member_roster.invalidate()


@transaction.atomic
def assign_covenant_role(
    *,
    character_sheet: CharacterSheet,
    covenant: Covenant,
    covenant_role: CovenantRole,
    rank: CovenantRank | None = None,
) -> CharacterCovenantRole:
    """Create a new active CharacterCovenantRole row. Atomic.

    If ``rank`` is not provided, the covenant's base rank (highest tier = lowest
    authority) is used.
    """
    effective_rank = rank if rank is not None else _ensure_base_rank(covenant)
    row = CharacterCovenantRole.objects.create(
        character_sheet=character_sheet,
        covenant=covenant,
        covenant_role=covenant_role,
        rank=effective_rank,
    )
    character_sheet.character.covenant_roles.invalidate()
    covenant.member_roster.invalidate()
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(character_sheet)
    return row


@transaction.atomic
def end_covenant_role(*, assignment: CharacterCovenantRole) -> None:
    """Mark an active assignment as ended. Idempotent. Un-engages first."""
    if assignment.left_at is not None:
        return
    assignment.engaged = False
    assignment.left_at = timezone.now()
    assignment.save(update_fields=["engaged", "left_at"])
    assignment.character_sheet.character.covenant_roles.invalidate()
    _invalidate_role_caches(assignment.character_sheet)
    assignment.covenant.member_roster.invalidate()
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(assignment.character_sheet)


@transaction.atomic
def leave_covenant(*, membership: CharacterCovenantRole) -> None:
    """A member voluntarily leaves a covenant. Soft-ends the membership, then
    auto-dissolves the covenant if active membership falls below the minimum.
    Idempotent: leaving an already-ended membership is a no-op.

    Raises LastManagerRankError if the member holds the last can_manage_ranks rank
    and the covenant would survive the departure (i.e. enough members remain).
    """
    if membership.left_at is not None:
        return
    covenant = membership.covenant
    departed_sheet = membership.character_sheet
    # Check dissolution: if the covenant will survive this departure, guard against
    # removing the last manager.  Count remaining members excluding this one.
    active_count_after = (
        covenant.memberships.filter(left_at__isnull=True).exclude(pk=membership.pk).count()
    )
    if active_count_after >= MINIMUM_FOUNDERS and membership.rank.can_manage_ranks:
        _assert_keeps_a_manager_excluding_membership(covenant, membership.pk)
    end_covenant_role(assignment=membership)
    if not _maybe_dissolve(covenant=covenant):
        _emit_departure_message(covenant, departed_sheet, kicked=False)


@transaction.atomic
def kick_member(*, target: CharacterCovenantRole, actor: CharacterCovenantRole) -> None:
    """Remove a member by rank authority. Soft-ends the target, then
    auto-dissolves if active membership falls below the minimum.
    Idempotent: kicking an already-departed member is a no-op.

    Authorization rules:
    - actor must be active (left_at IS NULL) and have rank.can_kick → NotAuthorizedToKickError
    - actor must be in the same covenant as target → NotAuthorizedToKickError
    - actor cannot kick themselves → CannotKickSelfError
    - actor.rank.tier must be strictly less than target.rank.tier
      (lower tier = higher authority) → CannotKickEqualOrHigherRankError
    """
    if actor.left_at is not None or not actor.rank.can_kick:
        raise NotAuthorizedToKickError
    if actor.covenant_id != target.covenant_id:
        # cross-covenant: defensive guard, UI-unreachable (targets are always same-covenant)
        raise NotAuthorizedToKickError
    if actor.pk == target.pk:
        raise CannotKickSelfError
    if actor.rank.tier >= target.rank.tier:
        # Equal or higher target tier means equal or superior authority — cannot kick.
        raise CannotKickEqualOrHigherRankError
    if target.left_at is not None:
        return
    covenant = target.covenant
    departed_sheet = target.character_sheet
    # Guard against management lock-out when the covenant will survive the kick.
    active_count_after = (
        covenant.memberships.filter(left_at__isnull=True).exclude(pk=target.pk).count()
    )
    if active_count_after >= MINIMUM_FOUNDERS and target.rank.can_manage_ranks:
        _assert_keeps_a_manager_excluding_membership(covenant, target.pk)
    end_covenant_role(assignment=target)
    if not _maybe_dissolve(covenant=covenant):
        _emit_departure_message(covenant, departed_sheet, kicked=True)


def _maybe_dissolve(*, covenant: Covenant) -> bool:
    """Dissolve the covenant if fewer than MINIMUM_FOUNDERS active members remain.
    Returns True if it dissolved. Idempotent via dissolve_covenant's guard."""
    remaining = covenant.member_roster.active_character_sheets
    if len(remaining) >= MINIMUM_FOUNDERS:
        return False
    recipients = list(remaining)  # capture before dissolve ends them
    dissolve_covenant(covenant=covenant)
    _emit_dissolution_message(covenant, recipients)
    return True


def _emit_departure_message(covenant: Covenant, departed: CharacterSheet, *, kicked: bool) -> None:
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheets = covenant.member_roster.active_character_sheets
    if not sheets:
        return
    verb = "has been cast out of" if kicked else "has left"
    send_narrative_message(
        recipients=sheets,
        body=f"{departed.character.db_key} {verb} the covenant '{covenant.name}'.",
        category=NarrativeCategory.COVENANT,
    )


def _emit_dissolution_message(covenant: Covenant, recipients: list[CharacterSheet]) -> None:
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if not recipients:
        return
    send_narrative_message(
        recipients=recipients,
        body=(
            f"The covenant '{covenant.name}' dissolves — too few remain to "
            "uphold the oath. Its bonds fall silent, but its memory endures."
        ),
        category=NarrativeCategory.COVENANT,
    )


@transaction.atomic
def set_engaged_membership(*, membership: CharacterCovenantRole) -> None:
    """Engage this membership; un-engage other same-type rows for the same character.

    Atomic. The same-type un-engage step uses a filter on
    covenant.covenant_type, which is naturally type-scoped.

    Iterates and calls save() (rather than bulk update) so SharedMemoryModel's
    identity-map cache stays in sync for rows already held in memory.
    """
    other_engaged = list(
        CharacterCovenantRole.objects.filter(
            character_sheet=membership.character_sheet,
            covenant__covenant_type=membership.covenant.covenant_type,
            engaged=True,
            left_at__isnull=True,
        ).exclude(pk=membership.pk)
    )
    for row in other_engaged:
        row.engaged = False
        row.save(update_fields=["engaged"])
    membership.engaged = True
    membership.save(update_fields=["engaged"])
    membership.character_sheet.character.covenant_roles.invalidate()
    _invalidate_role_caches(membership.character_sheet)
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(membership.character_sheet)


@transaction.atomic
def clear_engaged_membership(*, membership: CharacterCovenantRole) -> None:
    """Un-engage this membership. Idempotent."""
    if not membership.engaged:
        return
    membership.engaged = False
    membership.save(update_fields=["engaged"])
    membership.character_sheet.character.covenant_roles.invalidate()
    _invalidate_role_caches(membership.character_sheet)
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(membership.character_sheet)


@transaction.atomic
def clear_engaged_for_type(*, character_sheet: CharacterSheet, covenant_type: str) -> None:
    """Un-engage every engaged active membership of the given type for the character.

    Iterates and calls save() (rather than bulk update) so SharedMemoryModel's
    identity-map cache stays in sync for rows already held in memory.
    """
    rows = list(
        CharacterCovenantRole.objects.filter(
            character_sheet=character_sheet,
            covenant__covenant_type=covenant_type,
            engaged=True,
            left_at__isnull=True,
        )
    )
    if not rows:
        return
    for row in rows:
        row.engaged = False
        row.save(update_fields=["engaged"])
    character_sheet.character.covenant_roles.invalidate()
    _invalidate_role_caches(character_sheet)
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    recompute_max_health_with_threads(character_sheet)


def resolve_effective_role(*, character: Character, role: CovenantRole) -> CovenantRole:
    """Return the resonance-specialized sub-role for ``role`` if the character's
    anchored COVENANT_ROLE thread has crossed a sub-role's unlock_thread_level,
    else ``role`` unchanged. Derive-on-read; reads cached handlers only."""
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if role.parent_role_id is not None:
        return role  # already a sub-role; never re-promote (single-depth)
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role_id == role.pk
            and t.retired_at is None
        ),
        None,
    )
    if thread is None:
        return role
    best = None
    for sub in role.sub_roles.all():
        if (
            sub.resonance_id == thread.resonance_id
            and sub.unlock_thread_level <= thread.level
            and (best is None or sub.unlock_thread_level > best.unlock_thread_level)
        ):
            best = sub
    return best or role


def precedence_role_for_combat(character_sheet: CharacterSheet) -> CovenantRole | None:
    """Pick the single covenant role that governs combat for a character.

    Slice E precedence: when a character is engaged with both a Durance and a
    Battle covenant, the Battle role wins (it sets speed_rank / resolution
    order). Modifier bonuses still stack additively elsewhere
    (mechanics.covenant_role_bonus); this only chooses the one role attached to
    the CombatParticipant. At most one engaged role per type, so the result is
    deterministic.
    """
    from world.covenants.constants import CovenantType  # noqa: PLC0415

    engaged = character_sheet.character.covenant_roles.currently_engaged_roles()
    if not engaged:
        return None
    for role in engaged:
        if role.covenant_type == CovenantType.BATTLE:
            return role
    return engaged[0]


def is_gear_compatible(role: CovenantRole, archetype: str) -> bool:
    """Return True if a row exists in GearArchetypeCompatibility for this pair.

    Existence-only join lookup. Row present = role bonuses add to mundane gear
    stats on that archetype. Row absent = incompatible (max(role, gear) per
    slot). GearArchetypeCompatibility is authored content (SharedMemoryModel
    lookup table); identity-map cache makes repeated calls cheap.
    """
    return GearArchetypeCompatibility.objects.filter(
        covenant_role=role,
        gear_archetype=archetype,
    ).exists()


@transaction.atomic
def create_covenant_via_session(*, session: RitualSession) -> Covenant:
    """Dispatched on FORMATION fire. Unpacks the session into create_covenant args.

    Slice A's `create_covenant` enforces ≥2 founders, role-type compatibility,
    and atomic membership creation. This wrapper only adapts shape: read
    session_kwargs for the scalars, walk ACCEPTED participants for their
    chosen COVENANT_ROLE references, and call through.

    Per spec §4.6: the .filter() on `participant.references` (related manager)
    is in-mutator iteration on a tightly-scoped per-row set, not a cached
    handler lookup — acceptable exception to spec §3.9.
    """
    name: str = session.session_kwargs["name"]
    covenant_type: str = session.session_kwargs["covenant_type"]
    sworn_objective: str = session.session_kwargs["sworn_objective"]
    battle_binding: str = session.session_kwargs.get("battle_binding", "")

    founders: list[CovenantFounder] = []
    participants = list(session.participants.filter(state=ParticipantState.ACCEPTED))
    for p in participants:
        ref = p.references.filter(kind=ReferenceKind.COVENANT_ROLE).first()
        if ref is None:
            raise RequiredReferenceMissingError
        # The session initiator (first participant = session.initiator) is the default leader.
        is_leader = p.character_sheet_id == session.initiator_id
        founders.append(
            CovenantFounder(
                character_sheet=p.character_sheet,
                role=ref.ref_covenant_role,
                is_leader=is_leader,
            )
        )
    try:
        return create_covenant(
            name=name,
            covenant_type=covenant_type,
            sworn_objective=sworn_objective,
            founders=founders,
            battle_binding=battle_binding,
        )
    except IntegrityError as e:
        # Translate the DB-level uniqueness violation to a typed,
        # user-safe exception. Other integrity errors get re-raised
        # so they aren't accidentally masked.
        if _COVENANT_NAME_UNIQUE_MARKER in str(e).lower():
            raise CovenantNameConflictError from e
        raise


def _assert_keeps_a_manager(
    covenant: Covenant, *, exclude_rank: CovenantRank | None = None
) -> None:
    """Raise LastManagerRankError if the proposed change would leave zero active members
    holding a can_manage_ranks rank.

    Pass ``exclude_rank`` when the rank being deleted/demoted should not count toward
    the remaining-manager check (e.g. when reassigning all members away from it).
    """
    qs = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        left_at__isnull=True,
        rank__can_manage_ranks=True,
    )
    if exclude_rank is not None:
        qs = qs.exclude(rank=exclude_rank)
    if not qs.exists():
        raise LastManagerRankError


def _assert_keeps_a_manager_excluding_membership(
    covenant: Covenant, exclude_membership_pk: int
) -> None:
    """Raise LastManagerRankError if removing the given membership would leave zero
    active members holding a can_manage_ranks rank.

    Used by leave_covenant and kick_member to prevent management lock-out when the
    covenant has enough remaining members to survive (i.e. will not dissolve).
    """
    has_other_manager = (
        CharacterCovenantRole.objects.filter(
            covenant=covenant,
            left_at__isnull=True,
            rank__can_manage_ranks=True,
        )
        .exclude(pk=exclude_membership_pk)
        .exists()
    )
    if not has_other_manager:
        raise LastManagerRankError


@transaction.atomic
def create_rank(  # noqa: PLR0913
    *,
    covenant: Covenant,
    actor: CharacterCovenantRole,
    name: str,
    tier: int,
    can_invite: bool = False,
    can_kick: bool = False,
    can_manage_ranks: bool = False,
) -> CovenantRank:
    """Create a new rank in the covenant's ladder. Requires can_manage_ranks."""
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError
    rank = CovenantRank.objects.create(
        covenant=covenant,
        name=name,
        tier=tier,
        can_invite=can_invite,
        can_kick=can_kick,
        can_manage_ranks=can_manage_ranks,
    )
    covenant.member_roster.invalidate()
    return rank


@transaction.atomic
def rename_rank(*, rank: CovenantRank, actor: CharacterCovenantRole, name: str) -> CovenantRank:
    """Rename a rank. Requires can_manage_ranks."""
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError
    rank.name = name
    rank.save(update_fields=["name"])
    return rank


@transaction.atomic
def set_rank_capabilities(
    *,
    rank: CovenantRank,
    actor: CharacterCovenantRole,
    can_invite: bool | None = None,
    can_kick: bool | None = None,
    can_manage_ranks: bool | None = None,
) -> CovenantRank:
    """Update capability flags on a rank. Requires can_manage_ranks.

    Lock-out invariant: if demoting can_manage_ranks to False would leave no
    active member with a can_manage_ranks rank, raises LastManagerRankError.
    """
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError

    update_fields = []
    if can_invite is not None:
        rank.can_invite = can_invite
        update_fields.append("can_invite")
    if can_kick is not None:
        rank.can_kick = can_kick
        update_fields.append("can_kick")
    if can_manage_ranks is not None:
        rank.can_manage_ranks = can_manage_ranks
        update_fields.append("can_manage_ranks")

    # Check lock-out: if we're removing manage capability from this rank,
    # ensure other members still hold a can_manage_ranks rank.
    if "can_manage_ranks" in update_fields and not rank.can_manage_ranks:  # noqa: STRING_LITERAL
        _assert_keeps_a_manager(rank.covenant, exclude_rank=rank)

    if update_fields:
        rank.save(update_fields=update_fields)
    return rank


@transaction.atomic
def reorder_ranks(
    *,
    covenant: Covenant,
    actor: CharacterCovenantRole,
    ordered_rank_ids: list[int],
) -> list[CovenantRank]:
    """Rewrite tiers for the given ranks atomically and uniquely.

    ``ordered_rank_ids`` is a list of rank PKs in desired order (index 0 = top/tier 1).
    All PKs must belong to ``covenant``. Returns the updated ranks in order.
    Requires can_manage_ranks.
    """
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError

    all_rank_ids = set(CovenantRank.objects.filter(covenant=covenant).values_list("pk", flat=True))
    provided_ids = set(ordered_rank_ids)
    if provided_ids != all_rank_ids:
        raise IncompleteRankReorderError

    ranks = list(CovenantRank.objects.filter(covenant=covenant, pk__in=ordered_rank_ids))
    rank_map = {r.pk: r for r in ranks}
    n = len(ordered_rank_ids)

    # Assign unique temporary high-offset tiers first to avoid uniqueness conflicts mid-write.
    # Offset chosen to not collide with any existing tiers (n+1 … 2n).
    for idx, pk in enumerate(ordered_rank_ids):
        r = rank_map[pk]
        r.tier = n + idx + 1
        r.save(update_fields=["tier"])

    # Now assign the real tiers.
    result = []
    for idx, pk in enumerate(ordered_rank_ids):
        r = rank_map[pk]
        r.tier = idx + 1
        r.save(update_fields=["tier"])
        result.append(r)

    covenant.member_roster.invalidate()
    return result


@transaction.atomic
def delete_rank(
    *,
    rank: CovenantRank,
    actor: CharacterCovenantRole,
    reassign_to: CovenantRank,
) -> None:
    """Delete a rank after reassigning all active members to ``reassign_to``.

    Requires can_manage_ranks. Lock-out invariant: if the deleted rank held the
    last can_manage_ranks members (and reassign_to does not have can_manage_ranks),
    raises LastManagerRankError.

    CrossCovenantRankError if ``reassign_to`` belongs to a different covenant.
    """
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError
    if reassign_to.covenant_id != rank.covenant_id:
        raise CrossCovenantRankError

    # Check lock-out: exclude the rank being deleted if reassign_to doesn't manage.
    if not reassign_to.can_manage_ranks:
        _assert_keeps_a_manager(rank.covenant, exclude_rank=rank)

    # Reassign affected memberships via bulk update to avoid N individual saves.
    # Collect affected rows first (for cache invalidation), then update in bulk.
    affected = list(
        CharacterCovenantRole.objects.filter(
            covenant=rank.covenant,
            left_at__isnull=True,
            rank=rank,
        ).select_related("character_sheet__character")
    )
    CharacterCovenantRole.objects.filter(
        covenant=rank.covenant,
        left_at__isnull=True,
        rank=rank,
    ).update(rank=reassign_to)
    for membership in affected:
        # Flush the SharedMemoryModel identity-map entry so subsequent
        # refresh_from_db() calls see the updated rank_id from the DB.
        CharacterCovenantRole.flush_cached_instance(membership)
        membership.character_sheet.character.covenant_roles.invalidate()

    rank.delete()
    rank.covenant.member_roster.invalidate()


@transaction.atomic
def assign_rank(
    *,
    membership: CharacterCovenantRole,
    actor: CharacterCovenantRole,
    rank: CovenantRank,
) -> CharacterCovenantRole:
    """Assign a new rank to a member. Requires can_manage_ranks.

    Raises CrossCovenantRankError if rank.covenant != membership.covenant.
    Lock-out invariant: moving the last manager to a non-manager rank raises
    LastManagerRankError.
    """
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError
    if rank.covenant_id != membership.covenant_id:
        raise CrossCovenantRankError

    # Lock-out: if membership currently has manage cap and new rank doesn't,
    # ensure others still do.
    if membership.rank.can_manage_ranks and not rank.can_manage_ranks:
        _assert_keeps_a_manager(membership.covenant, exclude_rank=membership.rank)

    membership.rank = rank
    membership.save(update_fields=["rank"])
    membership.character_sheet.character.covenant_roles.invalidate()
    membership.covenant.member_roster.invalidate()
    return membership


@transaction.atomic
def transfer_top(
    *,
    covenant: Covenant,
    actor: CharacterCovenantRole,
    new_top_membership: CharacterCovenantRole,
) -> None:
    """Transfer the top rank (tier=1) from the actor to ``new_top_membership``.

    Requires can_manage_ranks. The actor is moved to the base rank (highest tier);
    new_top_membership is assigned the actor's current (top) rank.
    Raises CrossCovenantRankError if new_top_membership is in a different covenant.
    """
    if not actor.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError
    if new_top_membership.covenant_id != covenant.pk:
        raise CrossCovenantRankError
    if new_top_membership.left_at is not None:
        raise CannotTransferToDepartedMemberError

    top_rank = actor.rank
    base = _base_rank(covenant)

    # Move new_top_membership to the top rank.
    new_top_membership.rank = top_rank
    new_top_membership.save(update_fields=["rank"])
    new_top_membership.character_sheet.character.covenant_roles.invalidate()

    # Move actor to base rank.
    actor.rank = base
    actor.save(update_fields=["rank"])
    actor.character_sheet.character.covenant_roles.invalidate()

    # Belt-and-suspenders: ensure at least one active member still manages.
    _assert_keeps_a_manager(covenant)

    covenant.member_roster.invalidate()


def recompute_covenant_level(*, covenant: Covenant) -> int | None:
    """Look up the covenant's current legend total, find the max satisfied
    threshold, and update Covenant.level if changed.

    Returns the new level when the stored level rose, or None when unchanged.
    Fires one NarrativeMessage to engaged members when the level rises.

    Assumes the caller has an open atomic block (all call sites are wrapped
    in @transaction.atomic: create_solo_deed, create_legend_event, spread_deed,
    spread_event). No nested decorator needed.
    """
    from world.covenants.models import CovenantLevelThreshold  # noqa: PLC0415
    from world.societies.services import get_covenant_legend_total  # noqa: PLC0415

    total = get_covenant_legend_total(covenant)
    new_level = (
        CovenantLevelThreshold.objects.filter(required_legend__lte=total)
        .order_by("-level")
        .values_list("level", flat=True)
        .first()
    ) or 1
    if new_level == covenant.level:
        return None
    covenant.level = new_level
    covenant.save(update_fields=["level"])
    _emit_level_change_message(covenant, new_level)
    return new_level


def _emit_level_change_message(covenant: Covenant, new_level: int) -> None:
    """Fire one NarrativeMessage to engaged members on level change.

    send_narrative_message takes CharacterSheet recipients directly — no
    walk through RosterTenure → AccountDB needed.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    # The covenant.memberships related manager is fine here — one-shot lookup
    # on level-up, not a hot path. Walking every membership through the
    # SharedMemoryModel identity map would add no measurable benefit.
    sheets = [
        m.character_sheet
        for m in covenant.memberships.filter(  # noqa: SHARED_MEMORY
            engaged=True, left_at__isnull=True
        ).select_related("character_sheet")
    ]
    if not sheets:
        return
    send_narrative_message(
        recipients=sheets,
        body=f"The Covenant '{covenant.name}' has reached level {new_level}.",
        category=NarrativeCategory.COVENANT,
    )


@transaction.atomic
def rise_battle_covenant_via_session(*, session: RitualSession) -> Covenant:
    """Dispatched on a 'call the banners' rise ritual fire.

    Flips a dormant STANDING battle covenant to risen and engages the accepted
    participants who hold an active role there (Slice E). Mirrors
    create_covenant_via_session's session-unpacking shape.
    """
    from world.covenants.constants import BattleBinding, CovenantType  # noqa: PLC0415
    from world.covenants.exceptions import (  # noqa: PLC0415
        CovenantNotDormantError,
        NotAStandingBattleCovenantError,
    )

    ref = session.references.filter(kind=ReferenceKind.COVENANT).first()
    if ref is None or ref.ref_covenant is None:
        raise RequiredReferenceMissingError
    covenant = ref.ref_covenant
    if (
        covenant.covenant_type != CovenantType.BATTLE
        or covenant.battle_binding != BattleBinding.STANDING
    ):
        raise NotAStandingBattleCovenantError
    if not covenant.is_dormant:
        raise CovenantNotDormantError
    covenant.is_dormant = False
    covenant.save(update_fields=["is_dormant"])
    for p in session.participants.filter(state=ParticipantState.ACCEPTED):
        membership = CharacterCovenantRole.objects.filter(
            character_sheet=p.character_sheet,
            covenant=covenant,
            left_at__isnull=True,
        ).first()
        if membership is not None:
            set_engaged_membership(membership=membership)
    _emit_rise_message(covenant)
    return covenant


@transaction.atomic
def stand_down_battle_covenant(*, covenant: Covenant) -> None:
    """Stand a STANDING battle covenant down to dormant; clear engagement."""
    from world.covenants.constants import BattleBinding, CovenantType  # noqa: PLC0415
    from world.covenants.exceptions import NotAStandingBattleCovenantError  # noqa: PLC0415

    if (
        covenant.covenant_type != CovenantType.BATTLE
        or covenant.battle_binding != BattleBinding.STANDING
    ):
        raise NotAStandingBattleCovenantError
    covenant.is_dormant = True
    covenant.save(update_fields=["is_dormant"])
    for m in covenant.memberships.filter(  # noqa: SHARED_MEMORY
        engaged=True, left_at__isnull=True
    ).select_related("character_sheet"):
        m.engaged = False
        m.save(update_fields=["engaged"])
        m.character_sheet.character.covenant_roles.invalidate()
        _invalidate_role_caches(m.character_sheet)
        from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

        recompute_max_health_with_threads(m.character_sheet)


def _emit_rise_message(covenant: Covenant) -> None:
    """Fire one NarrativeMessage to engaged members when the banners are called."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheets = [
        m.character_sheet
        for m in covenant.memberships.filter(  # noqa: SHARED_MEMORY
            engaged=True, left_at__isnull=True
        ).select_related("character_sheet")
    ]
    if not sheets:
        return
    send_narrative_message(
        recipients=sheets,
        body=f"The banners are called — {covenant.name} rises to war once more.",
        category=NarrativeCategory.COVENANT,
    )


def evaluate_scene_engagement(
    *,
    character_sheet: CharacterSheet,
    room: ObjectDB,
) -> None:
    """Auto-engage a Durance covenant if co-presence prerequisites met, then
    fold the arriving character into any active rite in the room.

    Calls _auto_engage_durance first (which may set the engaged membership),
    then fold_arrival_into_active_rites so both newly-engaged and already-engaged
    characters trigger the rite buff rescale on arrival.
    """
    _auto_engage_durance(character_sheet=character_sheet, room=room)
    fold_arrival_into_active_rites(character_sheet=character_sheet, room=room)


def _auto_engage_durance(
    *,
    character_sheet: CharacterSheet,
    room: ObjectDB,
) -> None:
    """Auto-engage a Durance covenant if co-presence prerequisites met.

    Manual engagement sticks — this no-ops if the character is already
    engaged for the Durance type. See Slice B spec §3.6, §4.10.
    """
    from world.covenants.constants import CovenantType  # noqa: PLC0415
    from world.covenants.handlers import can_engage_membership  # noqa: PLC0415

    if (
        character_sheet.character.covenant_roles.currently_engaged_for_type(CovenantType.DURANCE)
        is not None
    ):
        return  # manual sticks; auto never overrides
    candidates: list[tuple[_CharacterCovenantRole, int]] = []
    for membership in character_sheet.character.covenant_roles.active_memberships_for_type(
        CovenantType.DURANCE
    ):
        if not can_engage_membership(membership):
            continue
        co_present = _co_present_member_count(membership, room)
        if co_present > 0:
            candidates.append((membership, co_present))
    if not candidates:
        return
    # Sort by most co-present (desc) then by covenant_id (asc) for deterministic ties:
    candidates.sort(key=lambda c: (-c[1], c[0].covenant_id))
    set_engaged_membership(membership=candidates[0][0])


def _rescale_other_participants(
    instance: CovenantRiteInstance,
    *,
    character_sheet: CharacterSheet,
    new_severity: int,
) -> None:
    """Ratchet every OTHER existing participant's live buff up to ``new_severity``."""
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        get_condition_instance,
    )

    other_records = instance.participant_records.exclude(
        character_sheet=character_sheet
    ).select_related("character_sheet", "granted_condition")
    for rec in other_records:
        live_inst = get_condition_instance(rec.character_sheet.character, rec.granted_condition)
        if live_inst is None:
            continue
        delta = new_severity - live_inst.severity
        if delta > 0:
            advance_condition_severity(live_inst, delta)


def _fold_arrival_into_covenant_rite(
    covenant_id: int,
    *,
    character_sheet: CharacterSheet,
    room: ObjectDB,
) -> None:
    """Fold the newcomer into this covenant's active rite in ``room`` (if any).

    No-op when there is no active rite instance for this covenant in the room,
    or when the character is already a participant.
    """
    from world.combat.constants import EncounterStatus  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    # Find an active rite instance for this covenant in this room.
    instance: CovenantRiteInstance | None = (
        CovenantRiteInstance.objects.filter(
            covenant_id=covenant_id,
            completed_at__isnull=True,
            combat_encounter__room=room,
        )
        .exclude(combat_encounter__status=EncounterStatus.COMPLETED)
        .select_related("rite", "rite__granted_condition")
        .first()
    )
    if instance is None:
        return
    if instance.participants.filter(pk=character_sheet.pk).exists():
        return  # already a participant — no-op

    # --- FOLD IN ---
    # Resolve the newcomer's role and pick their role-specific package.
    newcomer_ccr = (
        CharacterCovenantRole.objects.filter(
            character_sheet=character_sheet,
            covenant_id=covenant_id,
            left_at__isnull=True,
        )
        .select_related("covenant_role")
        .first()
    )
    newcomer_role = newcomer_ccr.covenant_role if newcomer_ccr is not None else None
    covenant_obj = Covenant.objects.get(pk=covenant_id)
    newcomer_template = instance.rite.package_for(newcomer_role, covenant_obj.level)

    # Record the newcomer participant with their own template.
    CovenantRiteParticipant.objects.create(
        instance=instance,
        character_sheet=character_sheet,
        granted_condition=newcomer_template,
    )
    new_count = instance.participants.count()
    new_severity = instance.rite.severity_for(present_count=new_count)

    # Apply the buff to the newcomer.
    apply_condition(
        character_sheet.character,
        newcomer_template,
        severity=new_severity,
        duration_rounds=instance.rite.duration_rounds,
        source_description="covenant rite",
    )

    # Rescale every OTHER existing participant's live buff upward if needed.
    _rescale_other_participants(
        instance, character_sheet=character_sheet, new_severity=new_severity
    )

    # Emit dramatic NarrativeMessage to all current participants.
    all_sheets = list(instance.participants.all())
    send_narrative_message(
        recipients=all_sheets,
        body=(f"{character_sheet.character.db_key} arrives — the covenant's oath blazes brighter."),
        category=NarrativeCategory.COVENANT,
    )


@transaction.atomic
def fold_arrival_into_active_rites(
    *,
    character_sheet: CharacterSheet,
    room: ObjectDB,
) -> None:
    """When an engaged member arrives in a room with an active CovenantRiteInstance,
    fold them in: grant the buff, rescale all current participants to the new
    severity (ratchet-up only), and emit a dramatic NarrativeMessage.

    Atomic. Safe to call even if the character is not a member of any covenant
    or there is no active rite — both paths are no-ops.
    """
    # Find all covenants this character is currently engaged with.
    engaged_covenants = list(
        CharacterCovenantRole.objects.filter(
            character_sheet=character_sheet,
            engaged=True,
            left_at__isnull=True,
        )
        .values_list("covenant_id", flat=True)
        .distinct()
    )
    if not engaged_covenants:
        return

    for covenant_id in engaged_covenants:
        _fold_arrival_into_covenant_rite(covenant_id, character_sheet=character_sheet, room=room)


def _co_present_member_count(
    membership: _CharacterCovenantRole,
    room: ObjectDB,
) -> int:
    """Count distinct other active members of `membership.covenant` in `room`.

    Uses cached handlers per project rule (spec §3.9) — no .filter() on
    related managers. The Character ↔ CharacterSheet accessor is `sheet_data`
    (reverse OneToOne).
    """
    self_sheet = membership.character_sheet
    target = membership.covenant
    n = 0
    for obj in room.contents:
        sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None or sheet == self_sheet:
            continue
        if sheet.character.covenant_roles.currently_held_role_in(target) is not None:
            n += 1
    return n


def covenant_members_present(*, covenant: Covenant, room: ObjectDB) -> list[CharacterSheet]:
    """CharacterSheets of active `covenant` members present in `room`.

    Builds the active-member set from the DB once, then walks room.contents —
    no per-object queries. The ≥N test is len(covenant_members_present(...)).
    Active means left_at__isnull=True; the engaged flag is not considered here.
    """
    active_sheet_ids = set(
        covenant.memberships.filter(left_at__isnull=True).values_list(
            "character_sheet_id", flat=True
        )
    )
    present: list[CharacterSheet] = []
    for obj in room.contents:
        sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is not None and sheet.pk in active_sheet_ids:
            present.append(sheet)
    return present


@transaction.atomic
def promote_to_subrole(
    *,
    membership: CharacterCovenantRole,
    target_subrole: CovenantRole,
) -> CharacterCovenantRole:
    """Promote a character from their current parent role to a sub-role.

    Validates:
    - target_subrole.parent_role == membership.covenant_role
    - The character has at least one Thread anchored on
      target_subrole.parent_role with resonance=target_subrole.resonance
      and level >= target_subrole.unlock_thread_level.

    Atomic. Closes the existing membership row (sets left_at) and creates
    a new active row with target_subrole, preserving the engaged flag.
    Reuses change_role mechanics underneath. Invalidates the
    character.covenant_roles handler cache.
    """
    if target_subrole.parent_role_id != membership.covenant_role_id:
        raise SubroleParentMismatchError
    # CharacterThreadHandler.all() returns list[Thread] — NOT a queryset.
    # No .filter() / .exists() — filter in Python.
    handler = membership.character_sheet.character.threads
    matching = [
        t
        for t in handler.all()
        if t.target_covenant_role_id == target_subrole.parent_role_id
        and t.resonance_id == target_subrole.resonance_id
    ]
    if not matching:
        raise SubroleResonanceMismatchError
    if not any(t.level >= target_subrole.unlock_thread_level for t in matching):
        raise SubroleThreadLevelInsufficientError
    # Reuse change_role: close old, open new with same engaged flag + preserve rank
    was_engaged = membership.engaged
    existing_rank = membership.rank
    end_covenant_role(assignment=membership)
    new_membership = assign_covenant_role(
        character_sheet=membership.character_sheet,
        covenant=membership.covenant,
        covenant_role=target_subrole,
        rank=existing_rank,
    )
    if was_engaged:
        set_engaged_membership(membership=new_membership)
    membership.character_sheet.character.covenant_roles.invalidate()
    return new_membership


def assert_initiator_can_induct(*, session: RitualSession) -> None:
    """Draft-time gate for INDUCTION rituals: the initiator must hold a can_invite
    rank in the target covenant. Dispatched via Ritual.draft_validator_path from
    draft_session. Reads the session-level COVENANT reference exactly like
    induct_member_via_session (the fire handler) does.
    """
    target_ref = session.references.filter(
        participant__isnull=True,
        kind=ReferenceKind.COVENANT,
    ).first()
    if target_ref is None or target_ref.ref_covenant is None:
        raise SessionTargetMissingError
    if not can_invite_to_covenant(target_ref.ref_covenant, character_sheet=session.initiator):
        raise NotAuthorizedToInviteError


@transaction.atomic
def induct_member_via_session(*, session: RitualSession) -> CharacterCovenantRole:
    """Dispatched on INDUCTION fire. Unpacks the session into add_member args.

    Walks the session-level COVENANT reference to get the target covenant,
    then finds the candidate — the one ACCEPTED participant with a
    COVENANT_ROLE reference. Existing-member participants have no role
    reference; they're just vouching.

    Per spec §4.6: the .filter() on `session.references` / `participant.references`
    (related managers) is in-mutator iteration on tightly-scoped per-row sets,
    not a cached handler lookup — acceptable exception to spec §3.9.
    """
    target_ref = session.references.filter(
        participant__isnull=True,
        kind=ReferenceKind.COVENANT,
    ).first()
    if target_ref is None or target_ref.ref_covenant is None:
        raise SessionTargetMissingError
    target_covenant = target_ref.ref_covenant

    # The candidate is the one ACCEPTED participant with a COVENANT_ROLE ref.
    candidate_participant = None
    chosen_role = None
    for p in session.participants.filter(state=ParticipantState.ACCEPTED):
        role_ref = p.references.filter(kind=ReferenceKind.COVENANT_ROLE).first()
        if role_ref is not None:
            candidate_participant = p
            chosen_role = role_ref.ref_covenant_role
            break
    if candidate_participant is None or chosen_role is None:
        raise RequiredReferenceMissingError
    return add_member(
        covenant=target_covenant,
        character_sheet=candidate_participant.character_sheet,
        role=chosen_role,
    )


@transaction.atomic
def complete_rites_for_encounter(*, encounter: CombatEncounter) -> None:
    """Sweep covenant rite buffs when a combat encounter ends.

    For each active CovenantRiteInstance tied to `encounter`, removes the
    granted_condition buff from every participant and stamps completed_at.

    Idempotent: instances already completed (completed_at is set) are
    excluded by the filter and will not be processed again.
    """
    from world.conditions.services import remove_condition  # noqa: PLC0415

    active_instances = list(
        CovenantRiteInstance.objects.filter(
            combat_encounter=encounter,
            completed_at__isnull=True,
        )
    )
    for instance in active_instances:
        for rec in instance.participant_records.select_related(
            "character_sheet", "granted_condition"
        ):
            remove_condition(rec.character_sheet.character, rec.granted_condition)
        instance.completed_at = timezone.now()
        instance.save(update_fields=["completed_at"])


@transaction.atomic
def perform_covenant_rite(*, session: RitualSession) -> CovenantRiteInstance:
    """Dispatched on fire of a RitualSession whose Ritual has a CovenantRite sidecar.

    Activation gate (all checked before any writes):
    1. Covenant ref present on the session.
    2. Covenant level ≥ rite.min_covenant_level.
    3. Active CombatEncounter present in the initiator's room.
    4. At least rite.min_members_present active members in the room.

    On success, creates a CovenantRiteInstance, sets participants, applies the
    scaled condition buff to each via bulk_apply_conditions, and emits a
    NarrativeMessage. Returns the new CovenantRiteInstance.
    """
    from world.combat.constants import EncounterStatus  # noqa: PLC0415
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
    from world.conditions.types import BulkConditionApplication  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    # 1. Resolve the CovenantRite sidecar from the session's ritual.
    rite: CovenantRite = session.ritual.covenant_rite

    # 2. Resolve the covenant from the session-level COVENANT reference.
    ref = session.references.filter(kind=ReferenceKind.COVENANT).first()
    if ref is None:
        raise CovenantRiteError
    covenant: Covenant = ref.ref_covenant

    # 3. Resolve room from initiator.
    room = session.initiator.character.db_location
    if room is None:
        raise NoActiveBattleError

    # 4a. Gate: covenant level.
    if covenant.level < rite.min_covenant_level:
        raise CovenantLevelTooLowError

    # 4b. Gate: active combat encounter in room.
    encounter = (
        CombatEncounter.objects.filter(room=room)
        .exclude(status=EncounterStatus.COMPLETED)
        .order_by("-id")
        .first()
    )
    if encounter is None:
        raise NoActiveBattleError

    # 4c. Gate: enough active covenant members present.
    beneficiaries = covenant_members_present(covenant=covenant, room=room)
    if len(beneficiaries) < rite.min_members_present:
        raise NotEnoughMembersPresentError

    # 5. Compute scaled severity.
    severity = rite.severity_for(present_count=len(beneficiaries))

    # 6. Create instance, record per-participant condition, and apply buffs.
    instance = CovenantRiteInstance.objects.create(
        rite=rite,
        covenant=covenant,
        scene=encounter.scene,
        combat_encounter=encounter,
    )
    role_by_sheet = {
        m.character_sheet_id: m.covenant_role
        for m in CharacterCovenantRole.objects.filter(
            character_sheet__in=[s.pk for s in beneficiaries],
            covenant=covenant,
            left_at__isnull=True,
        ).select_related("covenant_role")
    }
    applications = []
    for s in beneficiaries:
        template = rite.package_for(role_by_sheet[s.pk], covenant.level)
        CovenantRiteParticipant.objects.create(
            instance=instance, character_sheet=s, granted_condition=template
        )
        applications.append(
            BulkConditionApplication(
                target=s.character,
                template=template,
                severity=severity,
                duration_rounds=rite.duration_rounds,
            )
        )

    # 7. Apply the buff to each beneficiary.
    bulk_apply_conditions(applications, source_description="covenant rite")

    # 8. Emit drama.
    send_narrative_message(
        recipients=beneficiaries,
        body="The covenant reaffirms its oath — power surges through the gathered.",
        category=NarrativeCategory.COVENANT,
    )

    return instance


def get_mentor_bond_config() -> MentorBondConfig:
    """Return the seeded MentorBondConfig singleton (#1165).

    Uses get() — never get_or_create — because this is authored content; a
    fabricated row would silently break bond-scaling resolution.
    DoesNotExist propagates loudly. Mirrors get_flee_config.
    """
    return MentorBondConfig.objects.get(pk=1)


@transaction.atomic
def establish_mentor_bond_via_session(*, session: RitualSession) -> MentorBond:
    """Dispatched on Mentor's Vow BILATERAL fire. Wraps establish_mentor_bond.

    Reads the session-level COVENANT reference to get the target covenant.
    Discriminates the two ACCEPTED participants by participant_kwargs["role"]
    ("mentor" vs "sidekick") and delegates to establish_mentor_bond.

    Per spec §4.6: the .filter() calls on session.references and
    session.participants (related managers) are in-mutator iteration on
    tightly-scoped per-row sets — acceptable exception to spec §3.9.
    """
    from world.covenants.mentorship import establish_mentor_bond  # noqa: PLC0415

    covenant_ref = session.references.filter(
        participant__isnull=True,
        kind=ReferenceKind.COVENANT,
    ).first()
    if covenant_ref is None or covenant_ref.ref_covenant is None:
        raise SessionTargetMissingError

    covenant = covenant_ref.ref_covenant

    mentor_sheet: CharacterSheet | None = None
    sidekick_sheet: CharacterSheet | None = None

    for p in session.participants.filter(state=ParticipantState.ACCEPTED):
        role = p.participant_kwargs.get("role")
        if role == "mentor":  # noqa: STRING_LITERAL
            mentor_sheet = p.character_sheet
        elif role == "sidekick":  # noqa: STRING_LITERAL
            sidekick_sheet = p.character_sheet

    if mentor_sheet is None or sidekick_sheet is None:
        raise RequiredReferenceMissingError

    bond: MentorBond = establish_mentor_bond(
        covenant=covenant,
        mentor_sheet=mentor_sheet,
        sidekick_sheet=sidekick_sheet,
    )
    return bond
