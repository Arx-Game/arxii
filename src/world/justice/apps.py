from django.apps import AppConfig


class JusticeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.justice"
    verbose_name = "Justice"

    def ready(self) -> None:
        # Register the FRAME_JOB project-kind resolver with the projects framework
        # (#1825) — mirrors world.clues.apps' RESEARCH registration.
        from world.justice.frame_jobs import resolve_frame_job  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415

        register_kind_handler(ProjectKind.FRAME_JOB, resolve_frame_job)
