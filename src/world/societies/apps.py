"""Django app configuration for the societies system."""

from django.apps import AppConfig


class SocietiesConfig(AppConfig):
    """Configuration for the societies app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.societies"
    verbose_name = "Societies"

    def ready(self) -> None:
        # Import for side effect: registers the spread_a_tale scene-action resolver.
        from world.societies import spread_services  # noqa: F401, PLC0415
