"""Sanctum thread weaving + severing services (Plan 4 §F).

Players weave themselves into a Sanctum via one of three slot kinds:

- ``PERSONAL_OWN`` — the owner of a personal Sanctum (one slot per character)
- ``COVENANT`` — an active member of a covenant Sanctum (one slot per character)
- ``HELPER`` — an invited ally on someone else's personal Sanctum (unbounded)

Each weave creates a ``Thread`` row with ``target_kind=SANCTUM`` +
``target_sanctum_details`` FK + ``slot_kind`` populated; the partial
UniqueConstraints in the Thread model enforce slot uniqueness at the DB
layer. Personal Sanctums additionally cap total threads at the Sanctum's
level (read from ``RoomFeatureInstance.level``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.models import CharacterCovenantRole
from world.locations.constants import HolderType
from world.locations.services import effective_owner
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.models import Thread

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import SanctumDetails


class SanctumWeavingError(ValueError):
    user_message: str = "Cannot weave this Sanctum thread."


class SanctumWeavingNotOwnerError(SanctumWeavingError):
    user_message = "Only the Sanctum's owner can take the personal slot."


class SanctumWeavingNotCovenantMemberError(SanctumWeavingError):
    user_message = "Only active covenant members can weave into this Sanctum."


class SanctumWeavingHelperOnCovenantError(SanctumWeavingError):
    user_message = "Covenant Sanctums do not admit helper slots."


class SanctumWeavingHelperByOwnerError(SanctumWeavingError):
    user_message = "The Sanctum's owner cannot take a helper slot in their own Sanctum."


class SanctumWeavingLevelCapError(SanctumWeavingError):
    user_message = "This Sanctum has no remaining weaving slots at its current level."


class SanctumThreadNotFoundError(SanctumWeavingError):
    user_message = "No active thread to sever."


@transaction.atomic
def weave_sanctum_thread(
    sanctum: SanctumDetails,
    weaver: CharacterSheet,
    slot_kind: str,
) -> Thread:
    """Create a SANCTUM-target Thread for ``weaver`` on ``sanctum``.

    Validates per-mode standing and Personal-Sanctum level cap before
    creating the row. DB-layer partial UniqueConstraints on Thread
    additionally enforce one active PERSONAL_OWN / COVENANT per owner —
    if a duplicate slips past the service check it surfaces as
    IntegrityError.
    """
    _validate_weave_eligibility(sanctum, weaver, slot_kind)

    return Thread.objects.create(
        owner=weaver,
        resonance=sanctum.resonance_type,
        target_kind=TargetKind.SANCTUM,
        target_sanctum_details=sanctum,
        slot_kind=slot_kind,
    )


@transaction.atomic
def sever_sanctum_thread(thread: Thread) -> None:
    """Soft-retire a SANCTUM-target Thread (sets ``retired_at``).

    Retiring rather than deleting preserves the historical record + lets
    the partial-unique constraint admit a new active thread on the same
    (owner, sanctum, slot_kind) combination later. Pull / passive paths
    already exclude rows with ``retired_at IS NOT NULL``.
    """
    if thread.target_kind != TargetKind.SANCTUM:
        msg = "sever_sanctum_thread only operates on SANCTUM threads."
        raise SanctumThreadNotFoundError(msg)
    if thread.retired_at is not None:
        msg = f"Thread {thread.pk} is already retired."
        raise SanctumThreadNotFoundError(msg)
    thread.retired_at = timezone.now()
    thread.save(update_fields=["retired_at"])


_SLOT_VALIDATORS = {}  # populated below; one validator per SanctumSlotKind value


def _validate_weave_eligibility(
    sanctum: SanctumDetails,
    weaver: CharacterSheet,
    slot_kind: str,
) -> None:
    """Per-slot-kind permission + level-cap checks. Raises SanctumWeavingError subclasses."""
    room = sanctum.feature_instance.room_profile.objectdb
    ownership = effective_owner(room)
    if ownership is None:
        msg = f"Sanctum {sanctum.pk}'s room has no effective owner."
        raise SanctumWeavingNotOwnerError(msg)
    validator = _SLOT_VALIDATORS.get(slot_kind)
    if validator is None:
        msg = f"Unknown SanctumSlotKind: {slot_kind!r}"
        raise SanctumWeavingError(msg)
    validator(sanctum, weaver, ownership)


def _validate_personal_own(sanctum, weaver, ownership) -> None:
    if ownership.holder_type != HolderType.PERSONA:
        msg = "PERSONAL_OWN slot requires a personally-owned Sanctum."
        raise SanctumWeavingNotOwnerError(msg)
    if ownership.holder_persona.character_sheet_id != weaver.pk:
        msg = f"Weaver {weaver.pk} is not the owner of Sanctum {sanctum.pk}."
        raise SanctumWeavingNotOwnerError(msg)
    _check_personal_level_cap(sanctum)


def _validate_helper(sanctum, weaver, ownership) -> None:
    if ownership.holder_type != HolderType.PERSONA:
        msg = "HELPER slots only exist on personal Sanctums."
        raise SanctumWeavingHelperOnCovenantError(msg)
    if ownership.holder_persona.character_sheet_id == weaver.pk:
        msg = "Sanctum owner uses PERSONAL_OWN, not HELPER."
        raise SanctumWeavingHelperByOwnerError(msg)
    _check_personal_level_cap(sanctum)


def _validate_covenant(_sanctum, weaver, ownership) -> None:
    if ownership.holder_type != HolderType.ORGANIZATION:
        msg = "COVENANT slot requires a covenant-owned Sanctum."
        raise SanctumWeavingNotCovenantMemberError(msg)
    if ownership.holder_organization.org_type.name != COVENANT_ORG_TYPE_NAME:
        msg = "Sanctum's organization owner is not a Covenant."
        raise SanctumWeavingNotCovenantMemberError(msg)
    covenant = ownership.holder_organization.covenant
    active = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        character_sheet=weaver,
        left_at__isnull=True,
    ).exists()
    if not active:
        msg = f"Weaver {weaver.pk} is not an active member of covenant {covenant.pk}."
        raise SanctumWeavingNotCovenantMemberError(msg)
    # Covenant Sanctums skip the per-Sanctum level cap (spec §F table).


_SLOT_VALIDATORS.update(
    {
        SanctumSlotKind.PERSONAL_OWN: _validate_personal_own,
        SanctumSlotKind.HELPER: _validate_helper,
        SanctumSlotKind.COVENANT: _validate_covenant,
    }
)


def _check_personal_level_cap(sanctum: SanctumDetails) -> None:
    """Personal Sanctums cap total active SANCTUM threads at the level."""
    level = sanctum.feature_instance.level
    active_count = Thread.objects.filter(
        target_sanctum_details=sanctum,
        target_kind=TargetKind.SANCTUM,
        retired_at__isnull=True,
    ).count()
    if active_count >= level:
        msg = (
            f"Sanctum {sanctum.pk} is at level {level} with {active_count} "
            "active threads; level it up to weave more."
        )
        raise SanctumWeavingLevelCapError(msg)
