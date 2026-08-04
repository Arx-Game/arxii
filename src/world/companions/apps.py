def ready() -> None:
    """Register the stables room-feature strategy.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.companions`` stops being its own installed app.
    """
    from world.companions.services import handle_stables_progression  # noqa: PLC0415
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import register_room_feature_strategy  # noqa: PLC0415

    register_room_feature_strategy(
        RoomFeatureServiceStrategy.STABLES,
        handle_stables_progression,
        as_default=True,
    )
