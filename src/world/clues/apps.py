from django.apps import AppConfig


class CluesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.clues"
    verbose_name = "Clues"

    def ready(self) -> None:
        # Register the RESEARCH project-kind resolver with the projects framework
        # (#1146) — the same app-ready handshake buildings use for construction.
        from world.clues.research import resolve_research  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415

        register_kind_handler(ProjectKind.RESEARCH, resolve_research)
