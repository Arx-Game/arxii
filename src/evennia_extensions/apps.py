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

    def ready(self):
        """
        Called when the app is ready.
        """
        # Import signals or other app setup code here
        pass
