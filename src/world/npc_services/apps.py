"""AppConfig for the unified NPC services framework."""

from django.apps import AppConfig


class NPCServicesConfig(AppConfig):
    name = "world.npc_services"
    label = "npc_services"
    verbose_name = "NPC Services (offers, standing, interaction framework)"
    default_auto_field = "django.db.models.BigAutoField"
