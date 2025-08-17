"""
App configuration for evennia_extensions.
"""

from django.apps import AppConfig


class EvenniaExtensionsConfig(AppConfig):
    """
    Configuration for the evennia_extensions app.
    """

    name = "evennia_extensions"
    verbose_name = "Evennia Extensions"
    default_auto_field = "django.db.models.BigAutoField"
