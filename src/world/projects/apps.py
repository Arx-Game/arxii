"""AppConfig for the projects framework."""

from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = "world.projects"
    label = "projects"
    verbose_name = "Projects (delayed multi-tick endeavors)"
    default_auto_field = "django.db.models.BigAutoField"
