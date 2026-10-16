"""Startup hook for the worship system, called from world/apps.py (#3778)."""


def handle_shrine_progression(project, target_level: int, outcome_tier=None) -> None:  # noqa: ARG001
    """Shrines install through ``found_shrine`` and never upgrade; a progression
    project targeting the SHRINE kind is a content error, not a no-op."""
    msg = "Shrines are founded in place and have no upgrade path."
    raise ValueError(msg)


def ready() -> None:
    """Register the SHRINE room-feature strategy (its home app is worship), the
    deity's Codex companion (#4198) and the PLEDGE project kind (#4333)."""
    from world.codex.companions import register_companion  # noqa: PLC0415
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import register_room_feature_strategy  # noqa: PLC0415
    from world.worship.companion import being_companion  # noqa: PLC0415

    register_room_feature_strategy(
        RoomFeatureServiceStrategy.SHRINE, handle_shrine_progression, as_default=True
    )
    register_companion(being_companion)
    _register_pledge_kind()


def _register_pledge_kind() -> None:
    """The PLEDGE project kind (#4333 slice 2): its handler pays the closing or lapse
    award, and it is expiry-only, so reaching the favor target never resolves it."""
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import (  # noqa: PLC0415
        register_expiry_only_kind,
        register_kind_handler,
    )
    from world.worship.pledge_services import resolve_pledge_project  # noqa: PLC0415

    register_kind_handler(ProjectKind.PLEDGE, resolve_pledge_project)
    register_expiry_only_kind(ProjectKind.PLEDGE)
