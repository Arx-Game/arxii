"""Sanctum rituals — Ritual of Homecoming and Purging (Plan 4 §F).

Both rituals are authored as ``Ritual`` rows with ``execution_kind=SERVICE``;
the catalog seeds (``ensure_sanctum_rituals``) wire the rows' service
function paths to ``perform_homecoming_ritual`` and
``perform_purging_ritual``. Service-level validation (leader is owner /
covenant manager) is intentional per spec §F — the ``Ritual`` model
has no role-gating field, and adding one would migrate a generic table
for one-system needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.models import CharacterCovenantRole
from world.locations.constants import HolderType
from world.locations.services import effective_owner
from world.magic.constants import GainSource  # noqa: F401
from world.magic.exceptions import ResonanceInsufficient
from world.magic.models import CharacterResonance, SanctumOwnerMode
from world.magic.services.sanctum_lvm import (
    apply_homecoming_gain,
    drain_homecoming_for_purge,
    retag_homecoming_for_new_resonance,
    sum_homecoming_value,
)
from world.progression.services.skill_development import get_character_path_level

if TYPE_CHECKING:
    from world.magic.models import Resonance, SanctumDetails
    from world.scenes.models import Persona


PATH_LEVEL_CAP_MULTIPLIER = 10
"""Per-Path-level cap multiplier for personal Sanctum's Homecoming.

`cap = owner_character_path_level * PATH_LEVEL_CAP_MULTIPLIER`. Tunable.
"""

HOMECOMING_EFFICIENCY = 100
"""Resonance-sacrifice : base-resonance-gained ratio. Spec §F principle 1.1
weight — each unit of grown resonance costs 100 sacrificed."""

DEFAULT_PURGING_RETENTION = Decimal("0.5")
"""Fraction of Homecoming-grown resonance retained after Purging. Tunable."""

DEFAULT_PURGING_COST_MULTIPLIER = Decimal("1.0")
"""Sacrifice cost multiplier for Purging: at least this fraction of the
current Homecoming-grown sum must be paid from the leader's pool."""


class HomecomingValidationError(ValueError):
    user_message: str = "This Homecoming ritual cannot be performed."


class HomecomingLeaderNotOwnerError(HomecomingValidationError):
    user_message = "Only the Sanctum's owner can lead the Ritual of Homecoming."


class HomecomingLeaderNotCovenantMemberError(HomecomingValidationError):
    user_message = "You must be an active covenant member to lead this Homecoming."


class PurgingValidationError(ValueError):
    user_message: str = "This Purging ritual cannot be performed."


class PurgingResonanceTypeUnchangedError(PurgingValidationError):
    user_message = "Purging must change the Sanctum to a different resonance type."


@dataclass(frozen=True)
class HomecomingResult:
    """Frozen return shape for Homecoming runs."""

    base_resonance_added: int
    overflow_escrowed: int
    new_homecoming_sum: int
    new_cap: int


@dataclass(frozen=True)
class PurgingResult:
    """Frozen return shape for Purging runs."""

    new_resonance_id: int
    sum_after_drain: int
    sacrifice_paid: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_leader_for_sanctum(sanctum: SanctumDetails, leader_persona: Persona) -> None:
    """Personal: leader is the room owner. Covenant: leader is active covenant member.

    Raises HomecomingLeaderNotOwnerError / HomecomingLeaderNotCovenantMemberError.
    """
    room = sanctum.feature_instance.room_profile.objectdb
    ownership = effective_owner(room)
    if ownership is None:
        msg = (
            f"Sanctum {sanctum.pk}'s room has no effective owner; cannot validate "
            "ritual leadership."
        )
        raise HomecomingLeaderNotOwnerError(msg)

    if sanctum.owner_mode == SanctumOwnerMode.PERSONAL:
        if (
            ownership.holder_type != HolderType.PERSONA
            or ownership.holder_persona_id != leader_persona.pk
        ):
            msg = f"Leader persona {leader_persona.pk} is not the owner of Sanctum {sanctum.pk}."
            raise HomecomingLeaderNotOwnerError(msg)
        return

    # COVENANT path
    if ownership.holder_type != HolderType.ORGANIZATION:
        msg = (
            f"Sanctum {sanctum.pk} is marked COVENANT but the room's owner is not an Organization."
        )
        raise HomecomingLeaderNotCovenantMemberError(msg)
    if ownership.holder_organization.org_type.name != COVENANT_ORG_TYPE_NAME:
        msg = (
            f"Sanctum {sanctum.pk}'s organization owner is not a Covenant (org_type.name mismatch)."
        )
        raise HomecomingLeaderNotCovenantMemberError(msg)
    covenant = ownership.holder_organization.covenant
    active = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        character_sheet=leader_persona.character_sheet,
        left_at__isnull=True,
    ).exists()
    if not active:
        msg = (
            f"Leader persona {leader_persona.pk} is not an active member of covenant {covenant.pk}."
        )
        raise HomecomingLeaderNotCovenantMemberError(msg)


def _compute_cap(sanctum: SanctumDetails) -> int:
    """Per-Sanctum cap on Homecoming-grown resonance.

    Personal: ``owner_path_level × 10``. Covenant interim: sum of active
    member Path levels × 10 (will shift to ``Covenant.level`` when Slice D's
    level work ships per the spec note).
    """
    room = sanctum.feature_instance.room_profile.objectdb
    ownership = effective_owner(room)
    if ownership is None:
        return 0

    if sanctum.owner_mode == SanctumOwnerMode.PERSONAL:
        owner_persona = ownership.holder_persona
        character = owner_persona.character_sheet.character
        return get_character_path_level(character) * PATH_LEVEL_CAP_MULTIPLIER

    covenant = ownership.holder_organization.covenant
    active_sheets = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        left_at__isnull=True,
    ).values_list("character_sheet", flat=True)
    if not active_sheets:
        return 0
    total = 0
    for sheet_id in active_sheets:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        sheet = CharacterSheet.objects.get(pk=sheet_id)
        total += get_character_path_level(sheet.character)
    return total * PATH_LEVEL_CAP_MULTIPLIER


def _spend_from_leader_pool(leader_persona: Persona, resonance: Resonance, amount: int) -> None:
    """Deduct ``amount`` from leader's CharacterResonance balance. Raises if low."""
    cr = (
        CharacterResonance.objects.select_for_update()
        .filter(
            character_sheet=leader_persona.character_sheet,
            resonance=resonance,
        )
        .first()
    )
    if cr is None or cr.balance < amount:
        balance = cr.balance if cr is not None else 0
        msg = f"Leader needs {amount} resonance; balance is {balance}."
        raise ResonanceInsufficient(msg)
    cr.balance -= amount
    cr.save(update_fields=["balance"])


# ---------------------------------------------------------------------------
# Ritual of Homecoming
# ---------------------------------------------------------------------------


@transaction.atomic
def perform_homecoming_ritual(
    sanctum: SanctumDetails,
    leader_persona: Persona,
    resonance_sacrificed: int,
    narrative_text: str = "",  # noqa: ARG001
) -> HomecomingResult:
    """Sacrifice resonance to grow the Sanctum's Homecoming-source LVM row.

    Spec §F. 100:1 efficiency; cap is owner Path-level × 10 (Personal) or
    aggregate active-member Path levels × 10 (Covenant interim). Sacrifice
    above the cap is escrowed onto ``pending_sacrifice_overflow``; the cron
    tick absorbs escrow as cap rises (future work).
    """
    if resonance_sacrificed <= 0:
        msg = "Homecoming sacrifice must be positive."
        raise ResonanceInsufficient(msg)

    _validate_leader_for_sanctum(sanctum, leader_persona)
    _spend_from_leader_pool(leader_persona, sanctum.resonance_type, resonance_sacrificed)

    gain = resonance_sacrificed // HOMECOMING_EFFICIENCY
    cap = _compute_cap(sanctum)
    applied, overflow = apply_homecoming_gain(sanctum, gain, cap)

    sanctum.last_homecoming_ritual_at = timezone.now()
    if overflow > 0:
        sanctum.pending_sacrifice_overflow = sanctum.pending_sacrifice_overflow + Decimal(overflow)
        sanctum.save(update_fields=["last_homecoming_ritual_at", "pending_sacrifice_overflow"])
    else:
        sanctum.save(update_fields=["last_homecoming_ritual_at"])

    return HomecomingResult(
        base_resonance_added=applied,
        overflow_escrowed=overflow,
        new_homecoming_sum=sum_homecoming_value(sanctum),
        new_cap=cap,
    )


# ---------------------------------------------------------------------------
# Ritual of Purging
# ---------------------------------------------------------------------------


@transaction.atomic
def perform_purging_ritual(  # noqa: PLR0913
    sanctum: SanctumDetails,
    leader_persona: Persona,
    new_resonance: Resonance,
    resonance_sacrificed: int,
    retention: Decimal = DEFAULT_PURGING_RETENTION,
    cost_multiplier: Decimal = DEFAULT_PURGING_COST_MULTIPLIER,
) -> PurgingResult:
    """Change the Sanctum's consecrated resonance type, draining grown resonance.

    Spec §F. Steep cost: ``resonance_sacrificed >= sum_homecoming * cost_multiplier``.
    On success, the Sanctum's homecoming-source LVM rows are retagged to the
    new resonance type and multiplied by ``retention`` (0.5 = 50% retained;
    half is destroyed). Authored ambient + other sources on the same room
    are untouched.
    """
    _validate_leader_for_sanctum(sanctum, leader_persona)
    if new_resonance.pk == sanctum.resonance_type_id:
        msg = "Purging must change to a different resonance type."
        raise PurgingResonanceTypeUnchangedError(msg)

    current_sum = sum_homecoming_value(sanctum)
    required = int(Decimal(current_sum) * cost_multiplier)
    if resonance_sacrificed < required:
        msg = (
            f"Purging requires at least {required} resonance "
            f"({cost_multiplier}× current Homecoming sum of {current_sum})."
        )
        raise ResonanceInsufficient(msg)

    _spend_from_leader_pool(leader_persona, sanctum.resonance_type, resonance_sacrificed)

    # Order matters: retag first (rows still match the old source tag, just
    # adopt the new resonance FK), then drain (multiplies values by retention).
    retag_homecoming_for_new_resonance(sanctum, new_resonance)
    drain_homecoming_for_purge(sanctum, retention)

    sanctum.resonance_type = new_resonance
    sanctum.last_purging_ritual_at = timezone.now()
    sanctum.save(update_fields=["resonance_type", "last_purging_ritual_at"])

    return PurgingResult(
        new_resonance_id=new_resonance.pk,
        sum_after_drain=sum_homecoming_value(sanctum),
        sacrifice_paid=resonance_sacrificed,
    )
