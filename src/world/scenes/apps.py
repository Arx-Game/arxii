from django.apps import AppConfig


class ScenesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.scenes"

    def ready(self) -> None:
        # Import for the register_resolver("boon", ...) side effect (#2540) — the
        # same pattern societies uses for spread_services.
        from world.scenes import boon_services  # noqa: F401, PLC0415
