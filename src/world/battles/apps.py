"""App configuration for the battles system."""

from django.apps import AppConfig


class BattlesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.battles"
    verbose_name = "Battles"
