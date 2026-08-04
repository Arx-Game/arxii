def ready() -> None:
    """Register the Lab room-feature strategy + item-refinement handler.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.items`` stops being its own installed app.
    """
    # Register Lab as the LAB service strategy for the
    # ROOM_FEATURE_PROGRESSION ProjectKind handler (#1234).
    from world.items.crafting.station import handle_lab_progression  # noqa: PLC0415
    from world.room_features.constants import (  # noqa: PLC0415
        RoomFeatureServiceStrategy,
    )
    from world.room_features.services import (  # noqa: PLC0415
        register_room_feature_strategy,
    )

    register_room_feature_strategy(
        RoomFeatureServiceStrategy.LAB,
        handle_lab_progression,
    )

    # Item refinement (#2878): deterministic instant-completion projects —
    # the funded threshold IS the success; no outcome roll.
    from world.items.crafting.refinement import resolve_item_refinement  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import (  # noqa: PLC0415
        register_instant_completion_kind,
        register_kind_handler,
    )

    register_kind_handler(ProjectKind.ITEM_REFINEMENT, resolve_item_refinement)
    register_instant_completion_kind(ProjectKind.ITEM_REFINEMENT)
