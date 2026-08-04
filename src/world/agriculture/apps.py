def ready() -> None:
    """Register the field/granary room-feature strategies.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.agriculture`` stops being its own installed app.
    """
    from world.agriculture.services.handlers import (  # noqa: PLC0415
        handle_field_progression,
        handle_granary_progression,
    )
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import register_room_feature_strategy  # noqa: PLC0415

    register_room_feature_strategy(
        RoomFeatureServiceStrategy.FIELD,
        handle_field_progression,
    )
    register_room_feature_strategy(
        RoomFeatureServiceStrategy.GRANARY,
        handle_granary_progression,
    )
