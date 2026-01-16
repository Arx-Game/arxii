"""Django app configuration for custom admin functionality."""

from django.apps import AppConfig


class AdminConfig(AppConfig):
    """Configuration for the web.admin app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "web.admin"
    label = "web_admin"  # Avoid conflict with django.contrib.admin
    verbose_name = "Admin Customizations"
