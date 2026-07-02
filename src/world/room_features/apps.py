"""AppConfig for the room_features system."""

from django.apps import AppConfig


class RoomFeaturesConfig(AppConfig):
    name = "world.room_features"
    label = "room_features"
    verbose_name = "Room Features (Sanctum, Library, Training Room, …)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Register the ROOM_FEATURE_PROGRESSION Project handler so resolving
        # a completed install/upgrade project dispatches to the per-kind
        # service strategy. The strategy registry itself is populated by
        # each feature's home app (Sanctum: world.magic.services.sanctum).
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415
        from world.room_features.services import (  # noqa: PLC0415
            complete_room_feature_progression,
        )

        register_kind_handler(
            ProjectKind.ROOM_FEATURE_PROGRESSION,
            complete_room_feature_progression,
        )

        # COMMAND_CENTER (#930) is a generic feature — this app IS its home,
        # so its strategy registers here (Sanctum's registers from world.magic).
        from world.room_features.constants import (  # noqa: PLC0415
            RoomFeatureServiceStrategy,
        )
        from world.room_features.services import (  # noqa: PLC0415
            handle_command_center_progression,
            register_room_feature_strategy,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.COMMAND_CENTER,
            handle_command_center_progression,
        )
