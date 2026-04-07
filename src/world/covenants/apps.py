"""App configuration for the covenants system."""

from django.apps import AppConfig


class CovenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.covenants"
    verbose_name = "Covenants"
