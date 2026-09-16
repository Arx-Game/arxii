"""Startup hook for the worship system, called from world/apps.py (#3778)."""


def handle_shrine_progression(project, target_level: int, outcome_tier=None) -> None:  # noqa: ARG001
    """Shrines install through ``found_shrine`` and never upgrade; a progression
    project targeting the SHRINE kind is a content error, not a no-op."""
    msg = "Shrines are founded in place and have no upgrade path."
    raise ValueError(msg)


def ready() -> None:
    """Register the SHRINE room-feature strategy (its home app is worship)."""
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import register_room_feature_strategy  # noqa: PLC0415

    register_room_feature_strategy(
        RoomFeatureServiceStrategy.SHRINE, handle_shrine_progression, as_default=True
    )
