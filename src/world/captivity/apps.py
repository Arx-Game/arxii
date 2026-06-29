from django.apps import AppConfig


class CaptivityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.captivity"
    verbose_name = "Captivity"

    def ready(self) -> None:
        """Register the RANSOM project-kind handler + instant-completion (#1500)."""
        from world.captivity.ransom_project import resolve_ransom_project  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            register_instant_completion_kind,
            register_kind_handler,
        )

        register_kind_handler(ProjectKind.RANSOM, resolve_ransom_project)
        register_instant_completion_kind(ProjectKind.RANSOM)
