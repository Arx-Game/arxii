"""App configuration for the combat system."""

from django.apps import AppConfig


class CombatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.combat"
    verbose_name = "Combat"
