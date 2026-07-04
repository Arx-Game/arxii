"""AppConfig for the ships system (#1832)."""

from django.apps import AppConfig


class ShipsConfig(AppConfig):
    name = "world.ships"
    label = "ships"
    verbose_name = "Ships (persistent upgrades + repair)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Handler registration (upgrade/repair project kinds, etc.) lands in
        # later #1832 tasks once the underlying models/services exist.
        pass
