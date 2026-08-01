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

        # Item refinement (#2878): deterministic instant-completion projects —
        # the funded threshold IS the success; no outcome roll.
        from world.items.crafting.refinement import resolve_item_refinement  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            register_instant_completion_kind,
            register_kind_handler,
        )

        register_kind_handler(ProjectKind.ITEM_REFINEMENT, resolve_item_refinement)
        register_instant_completion_kind(ProjectKind.ITEM_REFINEMENT)
