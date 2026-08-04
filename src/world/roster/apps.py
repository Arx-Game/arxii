from django.apps import AppConfig


class RosterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.roster"

    def ready(self) -> None:
        """App ready - no signals to import per project policy."""
        ready()


def ready() -> None:
    """No signals to import per project policy.

    Extracted to module level so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.roster`` stops being its own installed app (#2906).
    """
