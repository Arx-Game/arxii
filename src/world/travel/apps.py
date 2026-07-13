"""AppConfig for the overworld travel system (#1855)."""

from django.apps import AppConfig


class TravelConfig(AppConfig):
    name = "world.travel"
    label = "travel"
    verbose_name = "Overworld Travel (voyages, hubs, routes)"
    default_auto_field = "django.db.models.BigAutoField"
