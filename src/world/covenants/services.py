"""Service functions for the covenants app."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.covenants.models import CharacterCovenantRole, CovenantRole


@transaction.atomic
def assign_covenant_role(
    *,
    character_sheet: CharacterSheet,
    covenant_role: CovenantRole,
) -> CharacterCovenantRole:
    """Create a new active CharacterCovenantRole row and invalidate handler cache.

    The model's partial unique constraint
    ``covenants_one_active_role_assignment`` enforces "at most one active
    assignment per (character, role)" at the DB level — duplicate active
    creates raise IntegrityError up the stack.
    """
    row = CharacterCovenantRole.objects.create(
        character_sheet=character_sheet,
        covenant_role=covenant_role,
    )
    character_sheet.character.covenant_roles.invalidate()
    return row


@transaction.atomic
def end_covenant_role(*, assignment: CharacterCovenantRole) -> None:
    """Mark an active assignment as ended (sets ``left_at``).

    Idempotent — already-ended assignments are no-ops. Invalidates the
    character's covenant_roles handler cache.
    """
    if assignment.left_at is not None:
        return
    assignment.left_at = timezone.now()
    assignment.save(update_fields=["left_at"])
    assignment.character_sheet.character.covenant_roles.invalidate()
