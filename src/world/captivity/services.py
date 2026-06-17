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

from django.db import IntegrityError, transaction
from django.utils import timezone

from world.captivity.constants import RESOLVED_STATUSES, CaptivityStatus
from world.captivity.exceptions import AlreadyCapturedError, NotHeldError
from world.captivity.models import Captivity, CaptivityConfig
from world.captivity.types import CaptureSetup
from world.character_sheets.types import LifecycleState
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.instances.services import complete_instanced_room, spawn_instanced_room

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.missions.models import MissionTemplate
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
    group_key: str | None = None,
    cell_name: str | None = None,
    cell_description: str | None = None,
) -> Captivity:
    """Take one character into a cell and record the captivity.

    Spawns a fresh cell unless ``cell`` is supplied (the explicit shared-cell
    path) or ``group_key`` matches an existing active cell (the keyed
    shared-cell path: captives of the same capture event reuse one cell — the
    consequence-effect path can't pass a cell object, so it passes a key).
    Flips the captive's lifecycle to CAPTURED and moves their body inside.

    Raises ``AlreadyCapturedError`` if the character is already held.
    """
    if Captivity.objects.filter(captive=captive, status=CaptivityStatus.HELD).exists():
        raise AlreadyCapturedError

    with transaction.atomic():
        if cell is None and group_key is not None:
            cell = _active_group_cell(group_key)
        if cell is None:
            room = spawn_instanced_room(
                name=cell_name or _DEFAULT_CELL_NAME,
                description=cell_description or _DEFAULT_CELL_DESCRIPTION,
                owner=captive,
                return_location=return_location,
                source_key=group_key or f"capture:{captive.pk}",
            )
            cell = room.instance_data

        captive.lifecycle_state = LifecycleState.CAPTURED
        captive.lifecycle_state_at = timezone.now()
        captive.save(update_fields=["lifecycle_state", "lifecycle_state_at"])

        try:
            captivity = Captivity.objects.create(
                captive=captive,
                cell=cell,
                captor_organization=captor_organization,
                offscreen_loss_allowed=offscreen_loss_allowed,
            )
        except IntegrityError as exc:
            # Lost a race against a concurrent capture — the partial unique
            # constraint (one HELD per captive) is the real guard; surface it
            # as the typed error the .exists() check above promises.
            raise AlreadyCapturedError from exc

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

    # Keep a reference to the cell before we detach from it — the resolved
    # captivity outlives the cell (its history is the point), so we null the
    # FK as part of the resolution save rather than trusting the cell's
    # deletion to propagate a grandchild SET_NULL through Evennia's delete.
    cell = captivity.cell

    with transaction.atomic():
        captivity.status = status
        captivity.resolved_at = timezone.now()
        captivity.cell = None
        captivity.save(update_fields=["status", "resolved_at", "cell"])

        captive = captivity.captive
        captive.lifecycle_state = LifecycleState.ALIVE
        captive.lifecycle_state_at = timezone.now()
        captive.save(update_fields=["lifecycle_state", "lifecycle_state_at"])

        # The captive is freed — tear down any discoverable rescue clues (#931 Phase 4)
        # so no stale rescue trail survives.
        from world.clues.services import clear_rescue_clues  # noqa: PLC0415

        clear_rescue_clues(captivity)

    # Relocate THIS captive ourselves — explicitly, before any teardown, and
    # whether or not they are puppeted. complete_instanced_room only moves
    # online occupants and would otherwise leave an offline freed captive in a
    # cell that is about to be deleted (the off-screen ransom case).
    _relocate_freed_captive(captivity.captive, cell)

    if cell is None:
        return
    others_still_held = Captivity.objects.filter(cell=cell, status=CaptivityStatus.HELD).exists()
    if others_still_held:
        return
    # Last one out: detach any remaining (already-resolved) captivities from
    # the cell, then tear the now-empty cell down.
    room = cell.room
    Captivity.objects.filter(cell=cell).update(cell=None)
    complete_instanced_room(room)


def rescue_captive(captive: CharacterSheet) -> bool:
    """Free a captive via rescue (#931 Phase 4) — a rescue run's terminal verb.

    Resolves the captive's active HELD captivity as ``RESCUED`` (flips lifecycle
    back to ALIVE, relocates them, tears the cell down once empty — all via
    :func:`resolve_captivity`). Idempotent: returns ``False`` if the captive is
    not currently held (already freed / never captured), so a double-fire of the
    rescue route is harmless.
    """
    captivity = Captivity.objects.filter(
        captive=captive,
        status=CaptivityStatus.HELD,
    ).first()
    if captivity is None:
        return False
    resolve_captivity(captivity, status=CaptivityStatus.RESCUED)
    return True


def resolve_capture_setup(  # noqa: PLR0913 — keyword-only; each arg is a distinct setup fact
    *,
    captive_template: MissionTemplate | None = None,
    rescue_template: MissionTemplate | None = None,
    cell_name: str = "",
    cell_description: str = "",
    clue_name: str = "",
    clue_description: str = "",
    clue_detect_difficulty: int | None = None,
) -> CaptureSetup:
    """Resolve one capture's loops + cell flavor: per-capture override, else default.

    Each argument is the value carried on the CAPTURE consequence effect (empty /
    ``None`` when that effect leaves it unset). Anything unset falls through to the
    one :class:`world.captivity.models.CaptivityConfig` singleton — so a marquee
    captor (an Ariwn dungeon) hand-crafts its own cell + loops via the effect while
    every routine capture lands on the one authored default.
    """
    config = CaptivityConfig.load()
    return CaptureSetup(
        captive_template=captive_template or config.captive_template,
        rescue_template=rescue_template or config.rescue_template,
        cell_name=cell_name or config.cell_name,
        cell_description=cell_description or config.cell_description,
        clue_name=clue_name or config.clue_name,
        clue_description=clue_description or config.clue_description,
        clue_detect_difficulty=(
            clue_detect_difficulty
            if clue_detect_difficulty is not None
            else config.clue_detect_difficulty
        ),
    )


def escape_captivity(captive: CharacterSheet) -> bool:
    """Free a captive by their own hand (#931 Phase 4) — the escape loop's verb.

    The terminal verb of the captive's escape option: resolves their active HELD
    captivity as ``ESCAPED`` (flips lifecycle back to ALIVE, relocates them, tears
    the cell down once empty — all via :func:`resolve_captivity`). Idempotent:
    returns ``False`` if the captive is not currently held, so a double-fire of a
    success route is harmless. The sibling of :func:`rescue_captive`, which ends the
    same captivity from an ally's side.
    """
    captivity = Captivity.objects.filter(
        captive=captive,
        status=CaptivityStatus.HELD,
    ).first()
    if captivity is None:
        return False
    resolve_captivity(captivity, status=CaptivityStatus.ESCAPED)
    return True


def _active_group_cell(group_key: str) -> InstancedRoom | None:
    """The still-active cell already spawned for this capture group, if any.

    Cells are tagged with the group key as their ``source_key``; a resolved
    group's cell is completed/torn down, so an ACTIVE match means the group is
    still being held and the next captive joins it (the shared-cell default).
    """
    return (
        InstancedRoom.objects.filter(source_key=group_key, status=InstanceStatus.ACTIVE)
        .order_by("-created_at")
        .first()
    )


def _relocate_freed_captive(captive: CharacterSheet, cell: InstancedRoom | None) -> None:
    """Move a freed captive out of the cell to where they belong.

    Destination: the cell's return location, falling back to the captive's
    home (the same fallback ``complete_instanced_room`` uses). No-op if neither
    exists or the character is gone.
    """
    character = captive.character
    if character is None:
        return
    destination = cell.return_location if cell is not None else None
    if destination is None:
        destination = character.home
    if destination is not None:
        character.move_to(destination, quiet=True)
