"""Service functions for the ships system (#1832).

- ``start_ship_construction`` — opens a ``SHIP_CONSTRUCTION`` Project + its
  ``ShipConstructionDetails`` payload for a persona (optionally a covenant
  deed-holder) commissioning a new ship.
- ``complete_ship_construction`` — the ``SHIP_CONSTRUCTION`` kind handler
  (registered in ``world.ships.apps.ready``): spawns the ``Building`` +
  entry (deck) room + ``ShipDetails`` exactly once.

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
)
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
