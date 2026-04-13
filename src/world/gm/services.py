"""GM system service functions for tables and memberships."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from world.gm.constants import GMTableStatus
from world.gm.models import GMProfile, GMTable, GMTableMembership
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

TEMPORARY_PERSONA_REJECTION = (
    "A temporary persona cannot join a GM table — use a primary or established persona."
)


@transaction.atomic
def create_table(gm: GMProfile, name: str, description: str = "") -> GMTable:
    """Create a new GM table owned by the given GM."""
    return GMTable.objects.create(gm=gm, name=name, description=description)


@transaction.atomic
def archive_table(table: GMTable) -> None:
    """Mark a table archived. Sets archived_at timestamp."""
    if table.status == GMTableStatus.ARCHIVED:
        return
    table.status = GMTableStatus.ARCHIVED
    table.archived_at = timezone.now()
    table.save(update_fields=["status", "archived_at"])


@transaction.atomic
def transfer_ownership(table: GMTable, new_gm: GMProfile) -> None:
    """Reassign a table to a different GM. Staff-only action."""
    table.gm = new_gm
    table.save(update_fields=["gm"])


@transaction.atomic
def join_table(table: GMTable, persona: Persona) -> GMTableMembership:
    """Add a persona to a table. Idempotent — returns existing active
    membership if one exists. Rejects TEMPORARY personas.
    """
    if persona.persona_type == PersonaType.TEMPORARY:
        raise ValidationError(TEMPORARY_PERSONA_REJECTION)
    existing = GMTableMembership.objects.filter(
        table=table,
        persona=persona,
        left_at__isnull=True,
    ).first()
    if existing:
        return existing
    return GMTableMembership.objects.create(table=table, persona=persona)


@transaction.atomic
def leave_table(membership: GMTableMembership) -> None:
    """Soft-leave a membership. No-op if already left."""
    if membership.left_at is not None:
        return
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_at"])


@transaction.atomic
def soft_leave_memberships_for_retired_persona(persona: Persona) -> int:
    """Future integration hook: called when a persona is retired.

    TODO: No production caller wired yet. When the persona retirement
    flow is implemented (likely as a service in world.scenes), it must
    call this to soft-leave any active table memberships. Without this,
    retired personas will retain active GM table memberships.

    Sets left_at on all active memberships for that persona. Returns
    the count of memberships closed.
    """
    now = timezone.now()
    count = 0
    for m in GMTableMembership.objects.filter(persona=persona, left_at__isnull=True):
        m.left_at = now
        m.save(update_fields=["left_at"])
        count += 1
    return count
