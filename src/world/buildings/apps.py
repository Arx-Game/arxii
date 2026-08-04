"""Startup hook for the buildings system, called from world/apps.py."""


def ready() -> None:
    """Replace the stub PERMIT handler and register project-kind handlers.

    Two cross-app registrations:
      1. Replace Plan 2's stub PERMIT effect handler with Plan 3's
         real `issue_permit`.
      2. Register `complete_building_construction` as the project
         framework's handler for BUILDING_CONSTRUCTION so resolving
         a completed construction project spawns the Building.
    Both go through helper functions so tests can roll back via
    reset_offer_effect_handlers / clear_kind_handlers.

    **Ordering is load-bearing (#2906):** this deliberately replaces the stub
    PERMIT effect handler `world.npc_services.effects` registers at import
    time. The single-app aggregator (``world.apps.ArxiiConfig.ready``) MUST
    call this in the same relative position INSTALLED_APPS gave it (after
    every ready() that runs before it there) — reordering silently changes
    which handler wins.
    """
    from world.buildings.condition_services import (  # noqa: PLC0415
        complete_building_preparation,
    )
    from world.buildings.fortification_services import (  # noqa: PLC0415
        complete_fortification_upgrade,
    )
    from world.buildings.property_grant_services import (  # noqa: PLC0415
        complete_building_activation,
    )
    from world.buildings.renovation_services import (  # noqa: PLC0415
        complete_building_renovation,
    )
    from world.buildings.room_services import (  # noqa: PLC0415
        complete_building_extension,
        complete_interior_design,
    )
    from world.buildings.services import (  # noqa: PLC0415
        complete_building_construction,
        issue_permit,
    )
    from world.buildings.upgrade_services import (  # noqa: PLC0415
        complete_building_upgrade,
    )
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.effects import register_offer_effect_handler  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import register_kind_handler  # noqa: PLC0415

    register_offer_effect_handler(OfferKind.PERMIT.value, issue_permit)
    register_kind_handler(ProjectKind.BUILDING_ACTIVATION, complete_building_activation)
    register_kind_handler(ProjectKind.BUILDING_CONSTRUCTION, complete_building_construction)
    register_kind_handler(ProjectKind.BUILDING_EXTENSION, complete_building_extension)
    register_kind_handler(ProjectKind.BUILDING_PREPARATION, complete_building_preparation)
    register_kind_handler(ProjectKind.BUILDING_RENOVATION, complete_building_renovation)
    register_kind_handler(ProjectKind.BUILDING_UPGRADE, complete_building_upgrade)
    register_kind_handler(ProjectKind.INTERIOR_DESIGN, complete_interior_design)
    register_kind_handler(ProjectKind.FORTIFICATION_UPGRADE, complete_fortification_upgrade)
