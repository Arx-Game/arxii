"""Django app configuration for the goals system."""

from django.apps import AppConfig


class GoalsConfig(AppConfig):
    """Configuration for the goals app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.goals"
    verbose_name = "Goals"
