"""Ship commission/upgrade/repair/status Actions (#1832 Task 8).

Thin REGISTRY wrappers over ``world.ships.services`` — the ``action.run()``
seam shared by telnet and the web dispatcher. ``CommissionShipAction`` opens
a brand-new ship's construction project (no existing ship to own yet, so it
only requires an active character). ``UpgradeShipAction``/``RepairShipAction``
are gated by ``IsShipOwnerPrerequisite`` — persistent investment in a ship
only the owner (persona or a member of the owning covenant) may authorize.
``ShipStatusAction`` is a read-only report, ungated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import (
    HasCharacterSheetPrerequisite,
    IsShipOwnerPrerequisite,
    Prerequisite,
)
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.ships.models import ShipDetails

#: ``UpgradeShipAction``'s third ``stat`` option — not a ``ShipUpgradeStat`` member
#: (hull is ``Building.fortification_level``, raised via ``start_ship_hull_upgrade``).
_HULL_STAT = "hull"


def _resolve_ship(actor: ObjectDB, kwargs: dict[str, Any]) -> ShipDetails | None:
    """The action's target ship: the ``ship`` kwarg (a ``ShipDetails``
    instance), else ``ship_id``, else the ship whose room the actor stands
    in. Mirrors ``IsShipOwnerPrerequisite``'s resolution so the same ship is
    gated and acted upon.
    """
    from world.ships.models import ShipDetails  # noqa: PLC0415

    ship = kwargs.get("ship")
    if ship is not None:
        return ship
    ship_id = kwargs.get("ship_id")
    if ship_id:
        return ShipDetails.objects.filter(pk=ship_id).select_related("building__entry_room").first()
    room = actor.location
    if room is None:
        return None
    return (
        ShipDetails.objects.filter(building__entry_room__objectdb=room)
        .select_related("building__entry_room")
        .first()
    )


@dataclass
class CommissionShipAction(Action):
    """Commission a new ship: opens a ``SHIP_CONSTRUCTION`` Project.

    Kwargs: ``ship_type`` (a ``ShipType``), ``name``, optional ``covenant``
    (the eventual deed-holder — see ``world.ships.services.start_ship_construction``).
    """

    key: str = "commission_ship"
    name: str = "Commission Ship"
    icon: str = "anchor"
    category: str = "ships"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: Any = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.ships.services import start_ship_construction  # noqa: PLC0415

        ship_type = kwargs.get("ship_type")
        name = (kwargs.get("name") or "").strip()
        if ship_type is None:
            return ActionResult(success=False, message="Pick a ship type.")
        if not name:
            return ActionResult(success=False, message="Name your ship.")
        persona = active_persona_for_sheet(actor.sheet_data)
        project = start_ship_construction(
            persona=persona,
            ship_type=ship_type,
            name=name,
            covenant=kwargs.get("covenant"),
        )
        return ActionResult(
            success=True,
            message=f"Construction of '{name}' commissioned (project #{project.pk}).",
            data={"project_id": project.pk},
        )


@dataclass
class UpgradeShipAction(Action):
    """Raise a persistent ship stat — handling/armament (``SHIP_UPGRADE``) or
    hull (``FORTIFICATION_UPGRADE``, via ``start_ship_hull_upgrade``).

    Kwargs: ``ship`` (a ``ShipDetails``; see ``_resolve_ship`` for the
    ``ship_id``/actor-location fallback), ``stat`` (``"handling"``,
    ``"armament"``, or ``"hull"``), ``target_level``.
    """

    key: str = "upgrade_ship"
    name: str = "Upgrade Ship"
    icon: str = "wrench"
    category: str = "ships"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsShipOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: Any = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.ships.constants import ShipUpgradeStat  # noqa: PLC0415
        from world.ships.exceptions import ShipError  # noqa: PLC0415
        from world.ships.services import (  # noqa: PLC0415
            start_ship_hull_upgrade,
            start_ship_upgrade,
        )

        ship = _resolve_ship(actor, kwargs)
        if ship is None:
            return ActionResult(success=False, message="No such ship.")
        stat = kwargs.get("stat")
        target_level = kwargs.get("target_level")
        if not stat or target_level is None:
            return ActionResult(success=False, message="Pick a stat and target level.")
        persona = active_persona_for_sheet(actor.sheet_data)
        try:
            if stat == _HULL_STAT:
                project = start_ship_hull_upgrade(
                    persona=persona, ship=ship, target_level=target_level
                )
            elif stat in ShipUpgradeStat.values:
                project = start_ship_upgrade(
                    persona=persona, ship=ship, stat=stat, target_level=target_level
                )
            else:
                return ActionResult(success=False, message=f"'{stat}' is not a valid stat.")
        except ShipError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValueError:
            return ActionResult(success=False, message="That upgrade is not valid.")
        return ActionResult(
            success=True,
            message=f"{stat.title()} upgrade to level {target_level} begins "
            f"(project #{project.pk}).",
            data={"project_id": project.pk},
        )


@dataclass
class RepairShipAction(Action):
    """Open a ``SHIP_REPAIR`` Project clearing the ship's ``needs_repair`` flag.

    Kwargs: ``ship`` (a ``ShipDetails``; see ``_resolve_ship`` for the
    ``ship_id``/actor-location fallback).
    """

    key: str = "repair_ship"
    name: str = "Repair Ship"
    icon: str = "hammer"
    category: str = "ships"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsShipOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: Any = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.ships.services import start_ship_repair  # noqa: PLC0415

        ship = _resolve_ship(actor, kwargs)
        if ship is None:
            return ActionResult(success=False, message="No such ship.")
        persona = active_persona_for_sheet(actor.sheet_data)
        project = start_ship_repair(persona=persona, ship=ship)
        return ActionResult(
            success=True,
            message=f"Repairs begin (project #{project.pk}).",
            data={"project_id": project.pk},
        )


@dataclass
class ShipStatusAction(Action):
    """Read-only report: a ship's effective stats and repair state.

    Kwargs: ``ship`` (a ``ShipDetails``; see ``_resolve_ship`` for the
    ``ship_id``/actor-location fallback).
    """

    key: str = "ship_status"
    name: str = "Ship Status"
    icon: str = "compass"
    category: str = "ships"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: Any = None,
        **kwargs: Any,
    ) -> ActionResult:
        ship = _resolve_ship(actor, kwargs)
        if ship is None:
            return ActionResult(success=False, message="No such ship.")
        data = {
            "ship_id": ship.pk,
            "effective_handling": ship.effective_handling(),
            "effective_armament": ship.effective_armament(),
            "effective_hull": ship.effective_hull(),
            "needs_repair": ship.needs_repair,
        }
        status = " (needs repair)" if ship.needs_repair else ""
        message = (
            f"{ship}: hull {data['effective_hull']}, handling {data['effective_handling']}, "
            f"armament {data['effective_armament']}{status}."
        )
        return ActionResult(success=True, message=message, data=data)
