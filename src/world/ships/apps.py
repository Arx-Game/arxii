"""AppConfig for the ships system (#1832)."""

from django.apps import AppConfig


class ShipsConfig(AppConfig):
    name = "world.ships"
    label = "ships"
    verbose_name = "Ships (persistent upgrades + repair)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # SHIP_UPGRADE / SHIP_REPAIR handler registration lands in later
        # #1832 tasks once their services exist.
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415
        from world.ships.services import complete_ship_construction  # noqa: PLC0415

        register_kind_handler(ProjectKind.SHIP_CONSTRUCTION, complete_ship_construction)
