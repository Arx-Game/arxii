"""Django app configuration for the societies system."""

from django.apps import AppConfig


class SocietiesConfig(AppConfig):
    """Configuration for the societies app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.societies"
    verbose_name = "Societies"

    def ready(self) -> None:
        # Register OrganizationType._name_cache for test-isolation flushing.
        from core.testing import register_test_cache_flusher  # noqa: PLC0415
        from world.societies.models import OrganizationType  # noqa: PLC0415

        register_test_cache_flusher(OrganizationType.clear_name_cache)
