"""Service functions for the ships system (#1832).

- ``start_ship_construction`` — opens a ``SHIP_CONSTRUCTION`` Project + its
  ``ShipConstructionDetails`` payload for a persona (optionally a covenant
  deed-holder) commissioning a new ship.
- ``complete_ship_construction`` — the ``SHIP_CONSTRUCTION`` kind handler
  (registered in ``world.ships.apps.ready``): spawns the ``Building`` +
  entry (deck) room + ``ShipDetails`` exactly once.
- ``start_ship_upgrade``/``complete_ship_upgrade`` — a persistent
  handling/armament investment (``SHIP_UPGRADE`` Project), monotonic
  max-set on completion, mirroring
  ``buildings.fortification_services.start_fortification_upgrade``.
- ``start_ship_hull_upgrade`` — a ship's hull is just
  ``Building.fortification_level``, so this is a thin wrapper delegating to
  the existing ``start_fortification_upgrade`` (``FORTIFICATION_UPGRADE``
  kind) rather than a new kind.
- ``start_ship_repair``/``complete_ship_repair`` — clears
  ``ShipDetails.needs_repair`` (``SHIP_REPAIR`` Project), gating further
  upgrades until resolved.

A ship is a ``buildings.Building`` (maritime ``BuildingKind``) decorated by
``ShipDetails`` — the same composition pattern ``Covenant`` uses over
``Organization``. Construction deliberately does NOT route through the
permit/contribution pipeline in ``world.buildings.services`` — permits,
material contributions, and size tiers are a House-specific authoring
surface a ship commission doesn't use. Instead this module reuses only the
low-level Area/Building/entry-room steps.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.ships.constants import (
    SHIP_BUILDING_SPACE_BUDGET,
    SHIP_BUILDING_TARGET_GRANDEUR,
    SHIP_BUILDING_TARGET_SIZE,
    SHIP_CONSTRUCTION_THRESHOLD,
    ShipUpgradeStat,
)
from world.ships.exceptions import ShipNeedsRepairError, ShipUpgradeError
from world.ships.seeds import ensure_ship_kind

if TYPE_CHECKING:
    from world.covenants.models import Covenant
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.ships.models import ShipDetails, ShipType


DECK_ROOM_NAME = "Main Deck"


def start_ship_construction(
    *,
    persona: Persona,
    ship_type: ShipType,
    name: str,
    covenant: Covenant | None = None,
) -> Project:
    """Open a ``SHIP_CONSTRUCTION`` Project commissioning a new ship.

    ``persona`` is always the commissioning/funding persona (the Project's
    ``owner_persona`` and weighted-check source at resolution). ``covenant``,
    when given, is the ship's eventual deed-holder — ``complete_ship_construction``
    grants it ownership of the ship's Area via ``LocationOwnership``, on top
    of (not instead of) crediting ``persona`` on the resulting ``Building``.

    Threshold/time-limit are PLACEHOLDER defaults, mirroring
    ``buildings.fortification_services.start_fortification_upgrade`` — real
    tuning per ``ShipType`` awaits a later content-authoring pass.
    """
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415
    from world.ships.models import ShipConstructionDetails  # noqa: PLC0415

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.SHIP_CONSTRUCTION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=SHIP_CONSTRUCTION_THRESHOLD,
            description=f"Construct {ship_type.name} '{name}'",
        )
        ShipConstructionDetails.objects.create(
            project=project,
            ship_type=ship_type,
            name=name,
            owner_persona=persona,
            owner_covenant=covenant,
        )
    return project


@transaction.atomic
def complete_ship_construction(
    project: Project,
    outcome_tier: object | None = None,  # noqa: ARG001
) -> ShipDetails:
    """Kind handler: spawn the ``Building`` + deck room + ``ShipDetails`` exactly once.

    Registered with ``world.projects.services.register_kind_handler`` at
    app-ready time. Signature matches the framework's ``KindHandler``
    callable (project, outcome_tier).

    Idempotent via the ``ShipConstructionDetails.applied_at`` claim idiom
    (mirrors ``buildings.fortification_services.complete_fortification_upgrade``):
    the ``filter(applied_at__isnull=True).update(...)`` hits the DB directly, so
    a second call on an already-completed project sees the non-null
    ``applied_at`` and returns the existing ``ShipDetails`` without re-creating
    anything.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.buildings.models import Building  # noqa: PLC0415
    from world.buildings.services import create_entry_room  # noqa: PLC0415
    from world.locations.services import transfer_ownership  # noqa: PLC0415
    from world.ships.models import ShipConstructionDetails, ShipDetails  # noqa: PLC0415

    now = timezone.now()
    claimed = ShipConstructionDetails.objects.filter(
        project=project, applied_at__isnull=True
    ).update(applied_at=now)
    details = ShipConstructionDetails.objects.select_related(
        "ship_type", "owner_covenant__organization", "resulting_ship"
    ).get(project=project)
    if not claimed:
        return details.resulting_ship
    # The .update() above is a raw SQL write — the idmapper identity map keeps
    # `details` as the same cached Python instance regardless, so its in-memory
    # applied_at wouldn't reflect that write unless set directly here too.
    details.applied_at = now

    ship_type = details.ship_type
    area = Area.objects.create(
        name=f"{ship_type.name} '{details.name}'",
        level=AreaLevel.BUILDING,
    )
    building = Building.objects.create(
        area=area,
        kind=ensure_ship_kind(),
        target_size=SHIP_BUILDING_TARGET_SIZE,
        target_grandeur=SHIP_BUILDING_TARGET_GRANDEUR,
        space_budget=SHIP_BUILDING_SPACE_BUDGET,
        fortification_level=ship_type.base_hull,
        owner_persona=details.owner_persona,
        constructed_by_persona=details.owner_persona,
        source_project=project,
    )
    entry_room = create_entry_room(building, DECK_ROOM_NAME)
    building.entry_room = entry_room
    building.save(update_fields=["entry_room"])

    ship = ShipDetails.objects.create(
        building=building,
        ship_type=ship_type,
        crew_capacity=ship_type.base_crew_capacity,
        cargo_capacity=ship_type.base_cargo_capacity,
    )

    if details.owner_covenant_id is not None:
        transfer_ownership(area=area, to_organization=details.owner_covenant.organization)

    details.resulting_ship = ship
    details.save(update_fields=["resulting_ship"])
    return ship


def start_ship_upgrade(
    *, persona: Persona, ship: ShipDetails, stat: str, target_level: int
) -> Project:
    """Open a ``SHIP_UPGRADE`` Project raising *ship*'s *stat* to *target_level*.

    Args:
        persona: The funding persona (project owner).
        ship: The ``ShipDetails`` whose handling/armament level this upgrades.
        stat: A ``ShipUpgradeStat`` value (``"handling"`` or ``"armament"``).
        target_level: The level this upgrade targets on completion. Must
            exceed the ship's current level for *stat*.

    Raises:
        ShipNeedsRepairError: If ``ship.needs_repair`` — a damaged ship must
            be repaired before further investment.
        ShipUpgradeError: If *stat* isn't a valid ``ShipUpgradeStat``, or
            *target_level* doesn't exceed the current level for *stat*.

    Returns:
        The newly created Project.
    """
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415
    from world.ships.constants import SHIP_UPGRADE_THRESHOLD_PER_LEVEL  # noqa: PLC0415
    from world.ships.models import ShipUpgradeDetails  # noqa: PLC0415

    if ship.needs_repair:
        raise ShipNeedsRepairError

    if stat not in ShipUpgradeStat.values:
        msg = f"'{stat}' is not a valid stat."
        raise ShipUpgradeError(msg)

    current_level = getattr(ship, f"{stat}_level")
    if target_level <= current_level:
        msg = f"That upgrade must target a higher {stat} level than the ship currently has."
        raise ShipUpgradeError(msg)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.SHIP_UPGRADE,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=target_level * SHIP_UPGRADE_THRESHOLD_PER_LEVEL,
            description=f"Raise {ship}'s {stat} level to {target_level}",
        )
        ShipUpgradeDetails.objects.create(
            project=project,
            ship=ship,
            stat=stat,
            target_level=target_level,
        )
    return project


@transaction.atomic
def complete_ship_upgrade(
    project: Project,
    outcome_tier: object | None = None,  # noqa: ARG001
) -> None:
    """Kind handler: raise the ship's stat level, exactly once, never downward.

    Registered with ``world.projects.services.register_kind_handler`` at
    app-ready time. Signature matches the framework's ``KindHandler``
    callable (project, outcome_tier).

    Idempotent via the ``ShipUpgradeDetails.applied_at`` claim idiom (mirrors
    ``buildings.fortification_services.complete_fortification_upgrade``): the
    ``filter(applied_at__isnull=True).update(...)`` hits the DB directly, so a
    second call on an already-completed project sees the non-null
    ``applied_at`` and returns without re-applying anything.
    """
    from world.ships.models import ShipUpgradeDetails  # noqa: PLC0415

    now = timezone.now()
    claimed = ShipUpgradeDetails.objects.filter(project=project, applied_at__isnull=True).update(
        applied_at=now
    )
    if not claimed:
        return
    details = ShipUpgradeDetails.objects.select_related("ship").get(project=project)
    # The .update() above is a raw SQL write — the idmapper identity map keeps
    # `details` as the same cached Python instance regardless, so its in-memory
    # applied_at wouldn't reflect that write unless set directly here too.
    details.applied_at = now

    ship = details.ship
    field_name = f"{details.stat}_level"
    current_level = getattr(ship, field_name)
    setattr(ship, field_name, max(current_level, details.target_level))
    ship.save(update_fields=[field_name])


def start_ship_hull_upgrade(*, persona: Persona, ship: ShipDetails, target_level: int) -> Project:
    """Open a hull upgrade for *ship*, reusing ``FORTIFICATION_UPGRADE``.

    A ship's hull IS ``Building.fortification_level`` — there's no separate
    hull stat or details model. This is a thin wrapper (after the shared
    ``needs_repair`` gate) delegating to
    ``buildings.fortification_services.start_fortification_upgrade``.

    Raises:
        ShipNeedsRepairError: If ``ship.needs_repair`` — a damaged ship must
            be repaired before further investment.
    """
    from world.buildings.fortification_services import (  # noqa: PLC0415
        start_fortification_upgrade,
    )

    if ship.needs_repair:
        raise ShipNeedsRepairError

    return start_fortification_upgrade(
        persona=persona, building=ship.building, target_level=target_level
    )


def start_ship_repair(*, persona: Persona, ship: ShipDetails) -> Project:
    """Open a ``SHIP_REPAIR`` Project clearing *ship*'s ``needs_repair`` flag.

    Args:
        persona: The funding persona (project owner).
        ship: The ``ShipDetails`` to repair.

    Returns:
        The newly created Project.
    """
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415
    from world.ships.constants import SHIP_REPAIR_THRESHOLD  # noqa: PLC0415
    from world.ships.models import ShipRepairDetails  # noqa: PLC0415

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.SHIP_REPAIR,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=SHIP_REPAIR_THRESHOLD,
            description=f"Repair {ship}",
        )
        ShipRepairDetails.objects.create(project=project, ship=ship)
    return project


@transaction.atomic
def complete_ship_repair(
    project: Project,
    outcome_tier: object | None = None,  # noqa: ARG001
) -> None:
    """Kind handler: clear the ship's ``needs_repair`` flag, exactly once.

    Registered with ``world.projects.services.register_kind_handler`` at
    app-ready time. Signature matches the framework's ``KindHandler``
    callable (project, outcome_tier).

    Idempotent via the ``ShipRepairDetails.applied_at`` claim idiom (mirrors
    ``complete_ship_upgrade``/``complete_ship_construction``).
    """
    from world.ships.models import ShipRepairDetails  # noqa: PLC0415

    now = timezone.now()
    claimed = ShipRepairDetails.objects.filter(project=project, applied_at__isnull=True).update(
        applied_at=now
    )
    if not claimed:
        return
    details = ShipRepairDetails.objects.select_related("ship").get(project=project)
    # The .update() above is a raw SQL write — the idmapper identity map keeps
    # `details` as the same cached Python instance regardless, so its in-memory
    # applied_at wouldn't reflect that write unless set directly here too.
    details.applied_at = now

    ship = details.ship
    ship.needs_repair = False
    ship.save(update_fields=["needs_repair"])
