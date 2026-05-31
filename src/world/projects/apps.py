"""AppConfig for the projects framework."""

from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = "world.projects"
    label = "projects"
    verbose_name = "Projects (delayed multi-tick endeavors)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Seed StatDefinition rows for project achievement stats.
        import contextlib  # noqa: PLC0415

        from django.db import OperationalError, ProgrammingError  # noqa: PLC0415

        from world.projects.services import register_stat_definitions  # noqa: PLC0415

        with contextlib.suppress(OperationalError, ProgrammingError):
            # DB not migrated yet (e.g., during makemigrations); skip silently.
            register_stat_definitions()
