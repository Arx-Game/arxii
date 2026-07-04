"""AppConfig for the ships system (#1832)."""

from django.apps import AppConfig


class ShipsConfig(AppConfig):
    name = "world.ships"
    label = "ships"
    verbose_name = "Ships (persistent upgrades + repair)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415
        from world.ships.services import (  # noqa: PLC0415
            complete_ship_construction,
            complete_ship_repair,
            complete_ship_upgrade,
        )

        register_kind_handler(ProjectKind.SHIP_CONSTRUCTION, complete_ship_construction)
        register_kind_handler(ProjectKind.SHIP_UPGRADE, complete_ship_upgrade)
        register_kind_handler(ProjectKind.SHIP_REPAIR, complete_ship_repair)
