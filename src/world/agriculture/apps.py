from django.apps import AppConfig


class AgricultureConfig(AppConfig):
    name = "world.agriculture"
    label = "agriculture"
    verbose_name = "Agriculture (Fields, Granaries, Food)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
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
