from django.apps import AppConfig


class MilitaryConfig(AppConfig):
    name = "world.military"
    label = "military"
    verbose_name = "Military (Persistent Units, Armies)"
    default_auto_field = "django.db.models.BigAutoField"
