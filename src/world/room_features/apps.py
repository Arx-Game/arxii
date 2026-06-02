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
