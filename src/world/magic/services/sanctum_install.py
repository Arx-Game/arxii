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

from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.models import CharacterCovenantRole
from world.locations.constants import HolderType
from world.locations.services import effective_owner
from world.magic.constants import GainSource
from world.magic.models import SanctumDetails, SanctumOwnerMode

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.magic.models import Resonance
    from world.magic.services.ritual_checks import OutcomeTier
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


class AbsorbError(ValueError):
    user_message: str = "Cannot absorb from this Sanctum."


class AbsorbNotPhysicallyPresentError(AbsorbError):
    user_message = "You must be physically in the Sanctum's room to absorb its gift."


class AbsorbNothingPendingError(AbsorbError):
    user_message = "The well is empty; nothing to absorb."


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------


# Outcome-tier recovery fractions (via ritual_checks.outcome_tier). TUNING PLACEHOLDERS.
DISSOLUTION_RECOVERY_CRIT_SUCCESS = Decimal("0.80")
DISSOLUTION_RECOVERY_SUCCESS = Decimal("0.50")
DISSOLUTION_RECOVERY_FAILURE = Decimal("0.10")
DISSOLUTION_RECOVERY_BOTCH = Decimal("0.0")


# ---------------------------------------------------------------------------
# Return shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanctificationResult:
    """Returned by perform_sanctification."""

    sanctum_id: int
    owner_mode: str
    resonance_type_id: int
    founder_character_sheet_id: int


@dataclass(frozen=True)
class DissolutionResult:
    """Returned by perform_dissolution.

    ``is_botch`` is True when the outcome tier is BOTCH (success_level ≤ −2).
    Callers wanting to surface "something bad happened" can read this flag;
    consequence content (status effects, magical mishaps) is future work.
    """

    sanctum_id: int
    success_level: int
    recovered_amount: int
    is_botch: bool


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
    COVENANT). Components are validated + consumed when the touchstone-
    item framework lands (#707); for now ``component_items`` is accepted
    but unused.
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

    # Service-level pre-check + DB partial UniqueConstraint together
    # close the race window. Two concurrent Sanctifications by the same
    # character would both see no row on the pre-check, race the create,
    # and the loser hits the constraint — caught below and re-raised as
    # the typed exception.
    if (
        owner_mode == SanctumOwnerMode.PERSONAL
        and SanctumDetails.objects.filter(
            founder_character_sheet=founder_sheet,
            owner_mode=SanctumOwnerMode.PERSONAL,
        ).exists()
    ):
        msg = (
            f"Character sheet {founder_sheet.pk} already founded a Personal Sanctum; "
            "Dissolve it before founding another."
        )
        raise SanctificationFounderHasPersonalSanctumError(msg)

    from django.db import IntegrityError  # noqa: PLC0415

    sanctum_kind = RoomFeatureKind.objects.get(name=SANCTUM_KIND_NAME)
    instance = RoomFeatureInstance.objects.create(
        room_profile=room_profile,
        feature_kind=sanctum_kind,
        level=1,
    )
    try:
        details = SanctumDetails.objects.create(
            feature_instance=instance,
            resonance_type=resonance_type,
            owner_mode=owner_mode,
            founder_character_sheet=founder_sheet,
        )
    except IntegrityError as exc:
        # Partial UniqueConstraint race loser path — convert the 500 into
        # a typed 400. The atomic wrapper rolls back the RoomFeatureInstance
        # create above.
        msg = (
            f"Character sheet {founder_sheet.pk} race-lost the partial "
            "UniqueConstraint for a Personal Sanctum."
        )
        raise SanctificationFounderHasPersonalSanctumError(msg) from exc
    return SanctificationResult(
        sanctum_id=details.pk,
        owner_mode=details.owner_mode,
        resonance_type_id=details.resonance_type_id,
        founder_character_sheet_id=founder_sheet.pk,
    )


def _validate_sanctification_leader(ownership, leader_persona: Persona, owner_mode: str) -> None:
    """Personal: leader = room owner persona. Covenant: leader = active covenant member."""
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
        msg = "Covenant Sanctification requires an organization-owned room."
        raise SanctificationLeaderNotCovenantMemberError(msg)
    if ownership.holder_organization.org_type.name != COVENANT_ORG_TYPE_NAME:
        msg = "The owning organization is not a Covenant."
        raise SanctificationLeaderNotCovenantMemberError(msg)
    covenant = ownership.holder_organization.covenant
    if not CharacterCovenantRole.objects.filter(
        covenant=covenant,
        character_sheet=leader_persona.character_sheet,
        left_at__isnull=True,
    ).exists():
        msg = (
            f"Leader persona {leader_persona.pk} is not an active member of covenant {covenant.pk}."
        )
        raise SanctificationLeaderNotCovenantMemberError(msg)


# ---------------------------------------------------------------------------
# Dissolution
# ---------------------------------------------------------------------------


@transaction.atomic
def perform_dissolution(sanctum: SanctumDetails, leader_persona: Persona) -> DissolutionResult:
    """Tear down the Sanctum with a tiered magical check.

    Difficulty is authored on the Ritual's RitualCheckConfig. Non-founder
    actors roll against ``non_founder_target_difficulty`` when set.
    Outcome tier (CRIT / SUCCESS / FAIL / BOTCH) determines the recovery
    fraction (see DISSOLUTION_RECOVERY_* constants).
    """
    from world.magic.seeds_sanctum import DISSOLUTION_RITUAL_NAME  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.magic.services.ritual_checks import (  # noqa: PLC0415
        OutcomeTier,
        perform_ritual_check,
    )
    from world.magic.services.sanctum_lvm import sum_homecoming_value  # noqa: PLC0415

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
    recovery_fraction = _dissolution_recovery_fraction(roll.tier)
    is_botch = roll.tier is OutcomeTier.BOTCH

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

    # SanctumDetails + RoomFeatureInstance + SanctumPendingPayout rows all
    # cascade from the RoomFeatureInstance deletion.
    instance = sanctum.feature_instance
    sanctum_pk = sanctum.pk
    instance.delete()

    return DissolutionResult(
        sanctum_id=sanctum_pk,
        success_level=success_level,
        recovered_amount=recovered_amount,
        is_botch=is_botch,
    )


def _dissolution_recovery_fraction(tier: OutcomeTier) -> Decimal:
    """Map check outcome tier to recovery fraction."""
    from world.magic.services.ritual_checks import OutcomeTier  # noqa: PLC0415

    if tier is OutcomeTier.CRIT:
        return DISSOLUTION_RECOVERY_CRIT_SUCCESS
    if tier is OutcomeTier.SUCCESS:
        return DISSOLUTION_RECOVERY_SUCCESS
    if tier is OutcomeTier.FAIL:
        return DISSOLUTION_RECOVERY_FAILURE
    return DISSOLUTION_RECOVERY_BOTCH


def _retire_sanctum_threads(sanctum: SanctumDetails) -> None:
    """Mass-retire (soft-delete) every SANCTUM-target Thread bound to this Sanctum."""
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
