"""AppConfig for the tasking framework."""

from django.apps import AppConfig


class TaskingConfig(AppConfig):
    name = "world.tasking"
    label = "tasking"
    verbose_name = "Tasking (org-issued NPC jobs)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        ready()


def ready() -> None:
    """App ready - no DB queries at import time.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.tasking`` stops being its own installed app.
    """
