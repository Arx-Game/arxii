from django.apps import AppConfig


class MagicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.magic"
    verbose_name = "Magic System"

    def ready(self) -> None:
        # Trigger registration of action resolvers and menu contributors.
        from world.magic.services import anima_ritual_action  # noqa: F401, PLC0415
