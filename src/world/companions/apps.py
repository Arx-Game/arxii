from django.apps import AppConfig


class CompanionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.companions"
    verbose_name = "Companions"

    def ready(self) -> None:
        from world.companions.services import handle_stables_progression  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.services import register_room_feature_strategy  # noqa: PLC0415

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.STABLES,
            handle_stables_progression,
        )
