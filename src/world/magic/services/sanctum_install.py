"""Sanctum install + dissolution + absorb services (Plan 4 §F Phase 4.1).

Three player-driven entry points:

- :func:`perform_sanctification` — Sanctification ritual creates the
  Sanctum at L1. Personal vs Covenant variant determined by ``owner_mode``
  kwarg (each ritual's service function passes the right value).
- :func:`perform_dissolution` — Tears down the Sanctum via a magical
  check. Outcome tier (BOTCH / FAILURE / SUCCESS / CRITICAL) determines
  what fraction of the imbued reservoir is recovered as resonance to
  the leader. Non-founder Dissolution applies a difficulty multiplier
  and a larger botch-consequence table.
- :func:`absorb_sanctum_pool` — Weaver physically visits the Sanctum
  room and drains their accumulated ``SanctumPendingPayout`` into their
  ``CharacterResonance`` balance via ``grant_resonance``.

Per Plan 4 §F revised 2026-06-03, these replace the Project-driven
install flow and the cron-tick direct-grant flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.constants import BOTCH_SUCCESS_LEVEL_MAX
from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.models import CharacterCovenantRole
from world.locations.constants import HolderType
from world.locations.services import effective_owner
from world.magic.constants import GainSource
from world.magic.models import SanctumDetails, SanctumOwnerMode

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.magic.models import Resonance
    from world.scenes.models import Persona


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SanctificationError(ValueError):
    user_message: str = "This Sanctification cannot be performed."


class SanctificationLeaderNotOwnerError(SanctificationError):
    user_message = "Only the room's owner can perform a Personal Sanctification."


class SanctificationLeaderNotCovenantMemberError(SanctificationError):
    user_message = "You must be an active covenant member to lead this Sanctification."


class SanctificationLeaderRankNotAuthorizedError(SanctificationLeaderNotCovenantMemberError):
    user_message = (
        "You are an active covenant member, but your rank doesn't have ritual-leadership authority."
    )


class SanctificationRoomNotOwnedError(SanctificationError):
    user_message = "No owner is recognized for this room; cannot found a Sanctum here."


class SanctificationRoomAlreadyHasFeatureError(SanctificationError):
    user_message = "This room already has a feature installed."


class SanctificationLeaderNotPresentError(SanctificationError):
    user_message = "You must be physically in the room to perform Sanctification."


class SanctificationFounderHasPersonalSanctumError(SanctificationError):
    user_message = "You already have a Personal Sanctum; dissolve the existing one first."


class DissolutionError(ValueError):
    user_message: str = "This Dissolution cannot be performed."


class DissolutionLeaderNotPresentError(DissolutionError):
    user_message = "You must be physically in the Sanctum's room to attempt Dissolution."


class DissolutionAlreadyDissolvedError(DissolutionError):
    user_message = "This Sanctum has already been dissolved."


class AbsorbError(ValueError):
    user_message: str = "Cannot absorb from this Sanctum."


class AbsorbNotPhysicallyPresentError(AbsorbError):
    user_message = "You must be physically in the Sanctum's room to absorb its gift."


class AbsorbNothingPendingError(AbsorbError):
    user_message = "The well is empty; nothing to absorb."


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------


SANCTIFICATION_CRIT_BONUS_IMBUE = 5
"""Bonus initial Homecoming imbue on a crit Sanctification. TUNING PLACEHOLDER."""

# success_level thresholds (canonical −10..+10 scale, mirroring the boundary
# constants formerly in ritual_checks.OutcomeTier's outcome_tier()).
MINIMUM_SANCTIFICATION_SUCCESS_LEVEL = 1
"""Below this, Sanctification fizzles (formerly OutcomeTier.FAIL/BOTCH)."""

SANCTIFICATION_CRIT_SUCCESS_LEVEL = 2
"""At/above this, Sanctification crits (formerly OutcomeTier.CRIT)."""

CRITICAL_FAILURE_SUCCESS_LEVEL = BOTCH_SUCCESS_LEVEL_MAX
"""At/below this, the roll is a Critical Failure (formerly OutcomeTier.BOTCH)."""


# ---------------------------------------------------------------------------
# Return shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanctificationResult:
    """Returned by perform_sanctification.

    On a failed or botched check, ``fizzled=True`` and ``sanctum_id=None`` —
    no state change occurred. On success or crit, ``fizzled=False`` and
    ``sanctum_id`` is the new SanctumDetails pk. ``tier`` is the rolled
    check's ``CheckOutcome.name`` so the API seam can surface the graded
    outcome without re-deriving the private tier boundaries.
    """

    sanctum_id: int | None
    owner_mode: str
    resonance_type_id: int
    founder_character_sheet_id: int
    success_level: int
    tier: str
    fizzled: bool = False


@dataclass(frozen=True)
class DissolutionResult:
    """Returned by perform_dissolution.

    ``is_botch`` is True when the outcome tier is BOTCH (success_level ≤ −2).
    Callers wanting to surface "something bad happened" can read this flag;
    consequence content (status effects, magical mishaps) is future work.
    ``tier`` is the rolled check's ``CheckOutcome.name`` for the API seam.
    """

    sanctum_id: int
    success_level: int
    recovered_amount: int
    is_botch: bool
    tier: str


def sanctification_fizzle_detail(success_level: int) -> str:
    """User-facing copy for a fizzled Sanctification, darker on a critical failure.

    A Critical Failure (success_level <= -2, formerly OutcomeTier.BOTCH) earns
    ominous copy — the rite went *wrong*, not merely failed to catch — while an
    ordinary Failure/Partial Success gets the gentler "failed to take hold" line.
    """
    if success_level <= CRITICAL_FAILURE_SUCCESS_LEVEL:
        return (
            "The ritual recoils — the rite goes wrong, the gathered power scatters "
            "and sours, and no Sanctum takes shape."
        )
    return "The ritual fails to take hold; the Sanctum was not created."


@dataclass(frozen=True)
class AbsorbResult:
    """Returned by absorb_sanctum_pool."""

    sanctum_id: int
    weaving_drained: int
    owner_bonus_drained: int
    total_drained: int


# ---------------------------------------------------------------------------
# Sanctification
# ---------------------------------------------------------------------------


@transaction.atomic
def perform_sanctification(
    room_profile: RoomProfile,
    leader_persona: Persona,
    resonance_type: Resonance,
    *,
    owner_mode: str,
    component_items: list | None = None,  # noqa: ARG001
) -> SanctificationResult:
    """Create the L1 Sanctum at ``room_profile``. Phase 4.1.

    Personal vs Covenant determined by ``owner_mode`` — each ritual's
    service function passes the right value (Ritual of Thine Own
    Sanctum → PERSONAL; Ritual of Blood Covenant Sanctification →
    COVENANT). Ritual of Sanctification's ``RitualComponentRequirement``
    rows (#707) are validated/consumed one layer up, in
    ``SanctumInstallAction.execute()`` (``resolve_and_consume_ritual_components``),
    BEFORE this function is ever called — Sanctification doesn't dispatch
    through the generic ``PerformRitualAction`` seam, so its bespoke Action
    is the only place that consumption can live. ``component_items`` here is
    vestigial (unused; no caller passes it) and may be removed in a future
    cleanup.
    """
    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureInstance,
        RoomFeatureKind,
    )
    from world.room_features.seeds import SANCTUM_KIND_NAME  # noqa: PLC0415

    ownership = effective_owner(room_profile.objectdb)
    if ownership is None:
        msg = f"Room {room_profile.pk} has no effective owner; cannot found a Sanctum."
        raise SanctificationRoomNotOwnedError(msg)

    _validate_sanctification_leader(ownership, leader_persona, owner_mode)

    # Physical presence — the witch performs Sanctification IN the room.
    character = leader_persona.character_sheet.character
    if character.db_location_id != room_profile.objectdb_id:
        msg = (
            f"Leader {leader_persona.pk} is not physically in room "
            f"{room_profile.pk}; cannot perform Sanctification."
        )
        raise SanctificationLeaderNotPresentError(msg)

    if RoomFeatureInstance.objects.filter(room_profile=room_profile).exists():
        msg = f"Room {room_profile.pk} already has a feature installed."
        raise SanctificationRoomAlreadyHasFeatureError(msg)

    founder_sheet = leader_persona.character_sheet
    # The partial UniqueConstraint excludes NULL founder rows from its
    # uniqueness scope. Reject NULL leader.character_sheet explicitly so
    # we don't quietly create a constraint-bypassing PERSONAL Sanctum.
    if founder_sheet is None:
        msg = "Sanctification leader must have a CharacterSheet."
        raise SanctificationLeaderNotOwnerError(msg)

    # Service-layer SELECT FOR UPDATE lock + pre-check (dissolved-excluding)
    # close the concurrent-founder race window. Two concurrent PERSONAL
    # sanctifications by the same founder both see no row on the pre-check
    # without the lock; the SELECT FOR UPDATE serializes them so only one
    # proceeds past the check. The DB UniqueConstraint was removed (cross-table
    # partial-unique limitation on dissolved_at); this service-layer lock is
    # now authoritative.
    if owner_mode == SanctumOwnerMode.PERSONAL:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        CharacterSheet.objects.select_for_update().get(pk=founder_sheet.pk)
        if SanctumDetails.objects.filter(
            founder_character_sheet=founder_sheet,
            owner_mode=SanctumOwnerMode.PERSONAL,
            feature_instance__dissolved_at__isnull=True,
        ).exists():
            msg = (
                f"Character sheet {founder_sheet.pk} already founded a Personal Sanctum; "
                "Dissolve it before founding another."
            )
            raise SanctificationFounderHasPersonalSanctumError(msg)

    # Roll the ritual check BEFORE creating any rows. Fizzle on fail/botch.
    from world.magic.seeds_sanctum import (  # noqa: PLC0415
        SANCTIFICATION_COVENANT_RITUAL_NAME,
        SANCTIFICATION_PERSONAL_RITUAL_NAME,
    )
    from world.magic.services.ritual_checks import perform_ritual_check  # noqa: PLC0415

    ritual_name = (
        SANCTIFICATION_PERSONAL_RITUAL_NAME
        if owner_mode == SanctumOwnerMode.PERSONAL
        else SANCTIFICATION_COVENANT_RITUAL_NAME
    )
    roll = perform_ritual_check(ritual_name, character)
    if roll.success_level < MINIMUM_SANCTIFICATION_SUCCESS_LEVEL:
        return SanctificationResult(
            sanctum_id=None,
            owner_mode=owner_mode,
            resonance_type_id=resonance_type.pk,
            founder_character_sheet_id=founder_sheet.pk,
            success_level=roll.success_level,
            tier=roll.check_result.outcome.name,
            fizzled=True,
        )

    sanctum_kind = RoomFeatureKind.objects.get(name=SANCTUM_KIND_NAME)
    instance = RoomFeatureInstance.objects.create(
        room_profile=room_profile,
        feature_kind=sanctum_kind,
        level=1,
    )
    details = SanctumDetails.objects.create(
        feature_instance=instance,
        resonance_type=resonance_type,
        owner_mode=owner_mode,
        founder_character_sheet=founder_sheet,
    )

    if roll.success_level >= SANCTIFICATION_CRIT_SUCCESS_LEVEL:
        from world.magic.services.sanctum_lvm import (  # noqa: PLC0415
            apply_homecoming_gain,
            compute_homecoming_cap,
        )

        apply_homecoming_gain(
            details, SANCTIFICATION_CRIT_BONUS_IMBUE, compute_homecoming_cap(details)
        )

    return SanctificationResult(
        sanctum_id=details.pk,
        owner_mode=details.owner_mode,
        resonance_type_id=details.resonance_type_id,
        founder_character_sheet_id=founder_sheet.pk,
        success_level=roll.success_level,
        tier=roll.check_result.outcome.name,
        fizzled=False,
    )


def _validate_sanctification_leader(ownership, leader_persona: Persona, owner_mode: str) -> None:
    """Personal: leader = room owner persona. Covenant: leader = active member with a
    can_lead_rituals rank."""
    if owner_mode == SanctumOwnerMode.PERSONAL:
        if (
            ownership.holder_type != HolderType.PERSONA
            or ownership.holder_persona_id != leader_persona.pk
        ):
            msg = (
                f"Leader persona {leader_persona.pk} is not the owner of this room; "
                "Personal Sanctification requires direct ownership."
            )
            raise SanctificationLeaderNotOwnerError(msg)
        return

    # COVENANT
    if ownership.holder_type != HolderType.ORGANIZATION:
        # NOTE: `user_message` (the class attribute below) is what reaches the
        # player, not this constructed `msg` — kept for exception __str__/logging.
        msg = "Covenant Sanctification requires an organization-owned room."
        raise SanctificationLeaderNotCovenantMemberError(msg)
    if not _covenant_ownership_allowed_for_sanctum():
        # NOTE: `user_message` (the class attribute below) is what reaches the
        # player, not this constructed `msg` — kept for exception __str__/logging.
        msg = "This room-feature kind does not permit covenant ownership."
        raise SanctificationLeaderNotCovenantMemberError(msg)
    if ownership.holder_organization.org_type.name != COVENANT_ORG_TYPE_NAME:
        # NOTE: `user_message` (the class attribute below) is what reaches the
        # player, not this constructed `msg` — kept for exception __str__/logging.
        msg = "The owning organization is not a Covenant."
        raise SanctificationLeaderNotCovenantMemberError(msg)
    covenant = ownership.holder_organization.covenant
    if not CharacterCovenantRole.objects.filter(
        covenant=covenant,
        character_sheet=leader_persona.character_sheet,
        left_at__isnull=True,
        rank__can_lead_rituals=True,
    ).exists():
        msg = (
            f"Leader persona {leader_persona.pk} is not authorized to lead Sanctification "
            f"for covenant {covenant.pk}: requires an active membership whose rank has "
            "ritual-leadership authority."
        )
        raise SanctificationLeaderRankNotAuthorizedError(msg)


def _covenant_ownership_allowed_for_sanctum() -> bool:
    """Whether the Sanctum RoomFeatureKind's authored catalog currently permits
    covenant ownership.

    Reads world.room_features.RoomFeatureKindOwnerType instead of assuming covenant
    ownership is always eligible — staff can revoke it via the authored catalog
    (admin-editable), closing the gap where this eligibility step was specified in
    the Plan 4 design (#669) but never actually wired.
    """
    from world.room_features.constants import RoomFeatureOwnerType  # noqa: PLC0415
    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureKind,
        RoomFeatureKindOwnerType,
    )
    from world.room_features.seeds import SANCTUM_KIND_NAME  # noqa: PLC0415

    sanctum_kind = RoomFeatureKind.objects.get(name=SANCTUM_KIND_NAME)
    return RoomFeatureKindOwnerType.objects.filter(
        feature_kind=sanctum_kind,
        owner_type=RoomFeatureOwnerType.ORGANIZATION_COVENANT,
    ).exists()


# ---------------------------------------------------------------------------
# Dissolution
# ---------------------------------------------------------------------------


@transaction.atomic
def perform_dissolution(sanctum: SanctumDetails, leader_persona: Persona) -> DissolutionResult:
    """Tear down the Sanctum with a tiered magical check.

    Difficulty is authored on the Ritual's RitualCheckConfig. Non-founder
    actors roll against ``non_founder_target_difficulty`` when set.
    Outcome tier determines the recovery fraction, looked up from the
    authored ``SanctumDissolutionRecoveryAward`` table.
    """
    from world.magic.seeds_sanctum import DISSOLUTION_RITUAL_NAME  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.magic.services.ritual_checks import perform_ritual_check  # noqa: PLC0415
    from world.magic.services.sanctum_lvm import sum_homecoming_value  # noqa: PLC0415

    # Idempotency guard — reject a second dissolution attempt.
    if sanctum.feature_instance.dissolved_at is not None:
        msg = f"Sanctum {sanctum.pk} is already dissolved."
        raise DissolutionAlreadyDissolvedError(msg)

    # Physical-presence gate — the witch is performing a ritual IN the
    # Sanctum's room. Mirrors absorb_sanctum_pool. Anyone with access
    # can attempt; founder vs non-founder difficulty differential lives
    # in the authored RitualCheckConfig, not as a hard authorization gate.
    sanctum_room = sanctum.feature_instance.room_profile.objectdb
    character = leader_persona.character_sheet.character
    if character.db_location_id != sanctum_room.pk:
        msg = (
            f"Leader {leader_persona.pk} is not physically in Sanctum room "
            f"{sanctum_room.pk}; cannot perform Dissolution."
        )
        raise DissolutionLeaderNotPresentError(msg)

    is_founder = sanctum.founder_character_sheet_id == leader_persona.character_sheet_id
    roll = perform_ritual_check(
        DISSOLUTION_RITUAL_NAME,
        leader_persona.character_sheet.character,
        founder_standing=is_founder,
    )
    success_level = roll.success_level
    recovery_fraction = _dissolution_recovery_fraction(roll.check_result.outcome)
    is_botch = success_level <= CRITICAL_FAILURE_SUCCESS_LEVEL

    reservoir_before = sum_homecoming_value(sanctum)
    recovered_amount = int(Decimal(reservoir_before) * recovery_fraction)

    # Tear down: threads, LVM rows, instance + details (cascade).
    _retire_sanctum_threads(sanctum)
    _delete_homecoming_lvm_rows(sanctum)

    if recovered_amount > 0:
        grant_resonance(
            character_sheet=leader_persona.character_sheet,
            resonance=sanctum.resonance_type,
            amount=recovered_amount,
            source=GainSource.SANCTUM_DISSOLUTION_RECOVERY,
            sanctum_details=sanctum,
        )

    # Soft-delete the RoomFeatureInstance. SanctumDetails + SanctumPendingPayout
    # rows are preserved (story-significant data must not be destroyed). The
    # dissolved instance is excluded from active reads via
    # ``feature_instance__dissolved_at__isnull=True`` filters on every read path.
    from django.utils import timezone  # noqa: PLC0415

    instance = sanctum.feature_instance
    sanctum_pk = sanctum.pk
    instance.dissolved_at = timezone.now()
    instance.save(update_fields=["dissolved_at"])

    return DissolutionResult(
        sanctum_id=sanctum_pk,
        success_level=success_level,
        recovered_amount=recovered_amount,
        is_botch=is_botch,
        tier=roll.check_result.outcome.name,
    )


def _dissolution_recovery_fraction(outcome: object) -> Decimal:
    """Look up the authored recovery fraction for this CheckOutcome tier."""
    from world.magic.models.sanctum import SanctumDissolutionRecoveryAward  # noqa: PLC0415

    return SanctumDissolutionRecoveryAward.objects.get(outcome_tier=outcome).recovery_fraction


def _retire_sanctum_threads(sanctum: SanctumDetails) -> None:
    """Soft-retire active SANCTUM threads targeting this sanctum.

    Stamps ``retired_at`` on every thread that is still active (``retired_at IS
    NULL``). Already-retired threads are left untouched. No thread is ever
    deleted — threads carry player investment (level/developed_points/XP-boundary
    receipts) and must survive for the historical record.

    The ``Thread.target_sanctum_details`` PROTECT FK is intentionally NOT cleared:
    the sanctum row itself is soft-deleted (``dissolved_at`` set) rather than
    removed, so the FK remains valid and the PROTECT constraint is never triggered.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    Thread.objects.filter(
        target_sanctum_details=sanctum,
        target_kind=TargetKind.SANCTUM,
        retired_at__isnull=True,
    ).update(retired_at=timezone.now())


def _delete_homecoming_lvm_rows(sanctum: SanctumDetails) -> None:
    """Delete the Sanctum's Homecoming-source LocationValueModifier rows."""
    from world.locations.models import LocationValueModifier  # noqa: PLC0415
    from world.magic.services.sanctum_lvm import homecoming_source_tag  # noqa: PLC0415

    LocationValueModifier.objects.filter(source=homecoming_source_tag(sanctum)).delete()


# ---------------------------------------------------------------------------
# Absorb
# ---------------------------------------------------------------------------


@transaction.atomic
def absorb_sanctum_pool(sanctum: SanctumDetails, weaver_persona: Persona) -> AbsorbResult:
    """Drain the weaver's pending pool from ``sanctum`` into their balance.

    Physical-presence required — the weaver's character must currently
    be located in the Sanctum's room. Pool is emptied in the same
    transaction as the ``grant_resonance`` calls; if any step raises,
    nothing drains.
    """
    from world.magic.models import SanctumPendingPayout  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    sanctum_room = sanctum.feature_instance.room_profile.objectdb
    character = weaver_persona.character_sheet.character
    if character.db_location_id != sanctum_room.pk:
        msg = (
            f"Weaver {weaver_persona.pk}'s character is not currently in Sanctum "
            f"room {sanctum_room.pk}."
        )
        raise AbsorbNotPhysicallyPresentError(msg)

    payout = (
        SanctumPendingPayout.objects.select_for_update()
        .filter(sanctum=sanctum, weaver_character_sheet=weaver_persona.character_sheet)
        .first()
    )
    if payout is None or payout.total_pending() == 0:
        msg = (
            f"No pending payout for weaver {weaver_persona.pk} at Sanctum "
            f"{sanctum.pk}; nothing to absorb."
        )
        raise AbsorbNothingPendingError(msg)

    weaving = payout.pending_weaving
    bonus = payout.pending_owner_bonus

    if weaving > 0:
        grant_resonance(
            character_sheet=weaver_persona.character_sheet,
            resonance=sanctum.resonance_type,
            amount=weaving,
            source=GainSource.SANCTUM_WEAVING,
            sanctum_details=sanctum,
        )
    if bonus > 0:
        grant_resonance(
            character_sheet=weaver_persona.character_sheet,
            resonance=sanctum.resonance_type,
            amount=bonus,
            source=GainSource.SANCTUM_OWNER_BONUS,
            sanctum_details=sanctum,
        )

    payout.pending_weaving = 0
    payout.pending_owner_bonus = 0
    payout.save(update_fields=["pending_weaving", "pending_owner_bonus", "updated_at"])

    return AbsorbResult(
        sanctum_id=sanctum.pk,
        weaving_drained=weaving,
        owner_bonus_drained=bonus,
        total_drained=weaving + bonus,
    )
