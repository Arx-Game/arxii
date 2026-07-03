from django.apps import AppConfig


class ItemsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.items"
    verbose_name = "Items & Equipment"

    def ready(self) -> None:
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
