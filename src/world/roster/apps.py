from django.apps import AppConfig


class RosterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.roster"

    def ready(self):
        """App ready - no signals to import per project policy."""
        pass
