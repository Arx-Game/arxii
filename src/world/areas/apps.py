from django.apps import AppConfig


class AreasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.areas"
    verbose_name = "Areas"

    def ready(self) -> None:
        # #1889 — register the CLEANUP kind handler + tiered resolver.
        from world.areas.cleanup_services import (  # noqa: PLC0415
            complete_cleanup,
            resolve_cleanup,
        )
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            register_kind_handler,
            register_tiered_resolver,
        )

        register_kind_handler(ProjectKind.CLEANUP, complete_cleanup)
        register_tiered_resolver(ProjectKind.CLEANUP, resolve_cleanup)
