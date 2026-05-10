"""Service functions for the covenants app."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantRole,
    GearArchetypeCompatibility,
)


@transaction.atomic
def create_covenant(
    *,
    name: str,
    covenant_type: str,
    sworn_objective: str,
    founder_character_sheet: CharacterSheet,
    founder_role: CovenantRole,
) -> Covenant:
    """Create a covenant with a single founder membership. Atomic."""
    cov = Covenant.objects.create(
        name=name,
        covenant_type=covenant_type,
        sworn_objective=sworn_objective,
    )
    CharacterCovenantRole.objects.create(
        character_sheet=founder_character_sheet,
        covenant=cov,
        covenant_role=founder_role,
    )
    founder_character_sheet.character.covenant_roles.invalidate()
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
