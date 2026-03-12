"""App configuration for the game clock system."""

from django.apps import AppConfig


class GameClockConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.game_clock"
    verbose_name = "Game Clock"
