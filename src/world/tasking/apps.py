"""AppConfig for the tasking framework."""

from django.apps import AppConfig


class TaskingConfig(AppConfig):
    name = "world.tasking"
    label = "tasking"
    verbose_name = "Tasking (org-issued NPC jobs)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """App ready - no DB queries at import time."""
