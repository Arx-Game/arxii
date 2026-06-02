from django.apps import AppConfig


class MagicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.magic"
    verbose_name = "Magic System"

    def ready(self) -> None:
        # Trigger registration of action resolvers and menu contributors.
        from world.magic.services import anima_ritual_action  # noqa: F401, PLC0415

        # Register Sanctum as the SANCTUM service strategy for the
        # ROOM_FEATURE_PROGRESSION ProjectKind handler (Plan 4 §F).
        from world.magic.services.sanctum import handle_progression  # noqa: PLC0415
        from world.room_features.constants import (  # noqa: PLC0415
            RoomFeatureServiceStrategy,
        )
        from world.room_features.services import (  # noqa: PLC0415
            register_room_feature_strategy,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.SANCTUM,
            handle_progression,
        )
