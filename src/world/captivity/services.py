"""Capture and release services (#931).

The mechanism the rest of prison & ransom hangs off: take a character into a
cell, and let them back out when the captivity ends. Capture rides the
existing instanced-room spawner (`world.instances`) and the existing
`CharacterSheet.lifecycle_state` machine — nothing here reinvents either.

Shared cells are the default. ``capture_party`` spawns one cell for a group;
``capture_character`` is the single-captive case (and is also the building
block ``capture_party`` calls, passing the shared cell down).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.captivity.constants import RESOLVED_STATUSES, CaptivityStatus
from world.captivity.exceptions import AlreadyCapturedError, NotHeldError
from world.captivity.models import Captivity
from world.character_sheets.types import LifecycleState
from world.instances.services import complete_instanced_room, spawn_instanced_room

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.instances.models import InstancedRoom
    from world.societies.models import Organization

# PLACEHOLDER cell flavor — rewrite in the project voice before launch.
_DEFAULT_CELL_NAME = "A Holding Cell"
_DEFAULT_CELL_DESCRIPTION = (
    "PLACEHOLDER. Cold stone, a barred door, and the particular quiet of a"
    " room built to keep someone in it."
)


def capture_character(  # noqa: PLR0913 — keyword-only; each arg is a distinct capture fact
    *,
    captive: CharacterSheet,
    captor_organization: Organization | None = None,
    return_location: ObjectDB | None = None,
    offscreen_loss_allowed: bool = False,
    cell: InstancedRoom | None = None,
    cell_name: str | None = None,
    cell_description: str | None = None,
) -> Captivity:
    """Take one character into a cell and record the captivity.

    Spawns a fresh cell unless ``cell`` is supplied (the shared-cell path).
    Flips the captive's lifecycle to CAPTURED and moves their body inside.

    Raises ``AlreadyCapturedError`` if the character is already held.
    """
    if Captivity.objects.filter(captive=captive, status=CaptivityStatus.HELD).exists():
        raise AlreadyCapturedError

    with transaction.atomic():
        if cell is None:
            room = spawn_instanced_room(
                name=cell_name or _DEFAULT_CELL_NAME,
                description=cell_description or _DEFAULT_CELL_DESCRIPTION,
                owner=captive,
                return_location=return_location,
                source_key=f"capture:{captive.pk}",
            )
            cell = room.instance_data

        captive.lifecycle_state = LifecycleState.CAPTURED
        captive.lifecycle_state_at = timezone.now()
        captive.save(update_fields=["lifecycle_state", "lifecycle_state_at"])

        captivity = Captivity.objects.create(
            captive=captive,
            cell=cell,
            captor_organization=captor_organization,
            offscreen_loss_allowed=offscreen_loss_allowed,
        )

    character = captive.character
    if character is not None:
        character.move_to(cell.room, quiet=True)
    return captivity


def capture_party(  # noqa: PLR0913 — keyword-only; each arg is a distinct capture fact
    *,
    captives: Iterable[CharacterSheet],
    captor_organization: Organization | None = None,
    return_location: ObjectDB | None = None,
    offscreen_loss_allowed: bool = False,
    cell_name: str | None = None,
    cell_description: str | None = None,
) -> list[Captivity]:
    """Capture several characters into one shared cell (the default).

    Spawns a single cell owned by the first captive and holds everyone in it.
    Returns the captivities in input order. Empty input is a no-op.
    """
    captives = list(captives)
    if not captives:
        return []

    room = spawn_instanced_room(
        name=cell_name or _DEFAULT_CELL_NAME,
        description=cell_description or _DEFAULT_CELL_DESCRIPTION,
        owner=captives[0],
        return_location=return_location,
        source_key=f"capture:party:{captives[0].pk}",
    )
    cell = room.instance_data

    return [
        capture_character(
            captive=captive,
            captor_organization=captor_organization,
            offscreen_loss_allowed=offscreen_loss_allowed,
            cell=cell,
        )
        for captive in captives
    ]


def resolve_captivity(captivity: Captivity, *, status: str) -> None:
    """End a captivity and free the captive.

    Flips the captive's lifecycle back to ALIVE. When this was the last held
    captive in the cell, the cell is completed (occupants relocated, room torn
    down if it holds no scene history); otherwise just this captive is moved
    back to the return location, leaving the shared cell standing for the rest.

    ``status`` must be one of the resolved (non-HELD) statuses. Raises
    ``NotHeldError`` if the captivity is already over.
    """
    if captivity.status != CaptivityStatus.HELD:
        raise NotHeldError
    if status not in RESOLVED_STATUSES:
        msg = f"{status!r} is not a resolved captivity status."
        raise ValueError(msg)

    with transaction.atomic():
        captivity.status = status
        captivity.resolved_at = timezone.now()
        captivity.save(update_fields=["status", "resolved_at"])

        captive = captivity.captive
        captive.lifecycle_state = LifecycleState.ALIVE
        captive.lifecycle_state_at = timezone.now()
        captive.save(update_fields=["lifecycle_state", "lifecycle_state_at"])

    others_still_held = Captivity.objects.filter(
        cell=captivity.cell, status=CaptivityStatus.HELD
    ).exists()
    if not others_still_held:
        complete_instanced_room(captivity.cell.room)
        return

    character = captivity.captive.character
    destination = captivity.cell.return_location
    if character is not None and destination is not None:
        character.move_to(destination, quiet=True)
