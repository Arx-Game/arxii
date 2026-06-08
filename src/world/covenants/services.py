"""Service functions for the covenants app."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.covenants.exceptions import (
    CovenantLevelTooLowError,
    CovenantNameConflictError,
    CovenantRiteError,
    DuplicateFounderError,
    InsufficientFoundersError,
    NoActiveBattleError,
    NotEnoughMembersPresentError,
    SubroleParentMismatchError,
    SubroleResonanceMismatchError,
    SubroleThreadLevelInsufficientError,
)
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantRite,
    CovenantRiteInstance,
    CovenantRiteParticipant,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.covenants.types import CovenantFounder
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.exceptions import RequiredReferenceMissingError, SessionTargetMissingError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter
    from world.covenants.models import CharacterCovenantRole as _CharacterCovenantRole
    from world.magic.models.sessions import RitualSession

MINIMUM_FOUNDERS = 2
_COVENANT_NAME_UNIQUE_MARKER = "name"  # substring in DB integrity error for name uniqueness


@transaction.atomic
def create_covenant(
    *,
    name: str,
    covenant_type: str,
    sworn_objective: str,
    founders: Sequence[CovenantFounder],
    battle_binding: str = "",
) -> Covenant:
    """Create a covenant with its initial set of founder memberships. Atomic.

    Covenants are inherently group structures — formation requires at least
    two distinct founders (`feedback_covenants_are_group_only.md`). The
    serializer layer enforces this for user-supplied data; the service
    raises typed exceptions as defensive assertions against programmer
    errors (Insufficient/DuplicateFounderError).
    """
    if len(founders) < MINIMUM_FOUNDERS:
        raise InsufficientFoundersError
    sheet_pks = [founder.character_sheet.pk for founder in founders]
    if len(set(sheet_pks)) != len(sheet_pks):
        raise DuplicateFounderError

    from world.covenants.constants import CovenantType  # noqa: PLC0415
    from world.covenants.exceptions import (  # noqa: PLC0415
        BattleBindingNotAllowedError,
        BattleBindingRequiredError,
    )

    if covenant_type == CovenantType.BATTLE:
        if not battle_binding:
            raise BattleBindingRequiredError
    elif battle_binding:
        raise BattleBindingNotAllowedError

    cov = Covenant.objects.create(
        name=name,
        covenant_type=covenant_type,
        sworn_objective=sworn_objective,
        battle_binding=battle_binding,
    )
    for founder in founders:
        CharacterCovenantRole.objects.create(
            character_sheet=founder.character_sheet,
            covenant=cov,
            covenant_role=founder.role,
        )
        founder.character_sheet.character.covenant_roles.invalidate()
    # The covenant is freshly created so its member_roster handler is new, but
    # invalidate for consistency in case the handler was accessed during this flow.
    cov.member_roster.invalidate()
    return cov


@transaction.atomic
def add_member(
    *,
    covenant: Covenant,
    character_sheet: CharacterSheet,
    role: CovenantRole,
) -> CharacterCovenantRole:
    """Create a new active membership row. Atomic.

    The active-uniqueness DB constraint enforces "at most one active role per
    (character, covenant)"; the IntegrityError on conflict is the contract.
    """
    row = CharacterCovenantRole.objects.create(
        character_sheet=character_sheet,
        covenant=covenant,
        covenant_role=role,
    )
    character_sheet.character.covenant_roles.invalidate()
    covenant.member_roster.invalidate()
    return row


@transaction.atomic
def change_role(
    *,
    membership: CharacterCovenantRole,
    new_role: CovenantRole,
) -> CharacterCovenantRole:
    """Close the existing membership row; create a new active row in the same covenant."""
    membership.engaged = False
    membership.left_at = timezone.now()
    membership.save(update_fields=["engaged", "left_at"])
    new_row = CharacterCovenantRole.objects.create(
        character_sheet=membership.character_sheet,
        covenant=membership.covenant,
        covenant_role=new_role,
    )
    membership.character_sheet.character.covenant_roles.invalidate()
    membership.covenant.member_roster.invalidate()
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
    covenant.member_roster.invalidate()


@transaction.atomic
def assign_covenant_role(
    *,
    character_sheet: CharacterSheet,
    covenant: Covenant,
    covenant_role: CovenantRole,
) -> CharacterCovenantRole:
    """Create a new active CharacterCovenantRole row. Atomic."""
    row = CharacterCovenantRole.objects.create(
        character_sheet=character_sheet,
        covenant=covenant,
        covenant_role=covenant_role,
    )
    character_sheet.character.covenant_roles.invalidate()
    covenant.member_roster.invalidate()
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
    assignment.covenant.member_roster.invalidate()


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


@transaction.atomic
def clear_engaged_membership(*, membership: CharacterCovenantRole) -> None:
    """Un-engage this membership. Idempotent."""
    if not membership.engaged:
        return
    membership.engaged = False
    membership.save(update_fields=["engaged"])
    membership.character_sheet.character.covenant_roles.invalidate()


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
    for p in session.participants.filter(state=ParticipantState.ACCEPTED):
        ref = p.references.filter(kind=ReferenceKind.COVENANT_ROLE).first()
        if ref is None:
            raise RequiredReferenceMissingError
        founders.append(
            CovenantFounder(
                character_sheet=p.character_sheet,
                role=ref.ref_covenant_role,
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
    from world.combat.constants import EncounterStatus  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        get_condition_instance,
    )
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

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
            continue
        if instance.participants.filter(pk=character_sheet.pk).exists():
            continue  # already a participant — no-op

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

        # Emit dramatic NarrativeMessage to all current participants.
        all_sheets = list(instance.participants.all())
        send_narrative_message(
            recipients=all_sheets,
            body=(
                f"{character_sheet.character.db_key} arrives — the covenant's oath blazes brighter."
            ),
            category=NarrativeCategory.COVENANT,
        )


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
    # Reuse change_role: close old, open new with same engaged flag
    was_engaged = membership.engaged
    end_covenant_role(assignment=membership)
    new_membership = assign_covenant_role(
        character_sheet=membership.character_sheet,
        covenant=membership.covenant,
        covenant_role=target_subrole,
    )
    if was_engaged:
        set_engaged_membership(membership=new_membership)
    membership.character_sheet.character.covenant_roles.invalidate()
    return new_membership


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
    4. At least rite.min_members_present engaged members in the room.

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
