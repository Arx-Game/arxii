# src/world/distinctions/apps.py
from django.apps import AppConfig


class DistinctionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.distinctions"
    verbose_name = "Distinctions"
