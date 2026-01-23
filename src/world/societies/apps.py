"""Django app configuration for the societies system."""

from django.apps import AppConfig


class SocietiesConfig(AppConfig):
    """Configuration for the societies app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.societies"
    verbose_name = "Societies"
