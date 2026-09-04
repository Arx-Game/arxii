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

    def ready(self) -> None:
        """Install the reload/shutdown lifecycle hook guard (issue #3195).

        Runs once per process, deterministically, before any request or
        management command executes -- the same guarantee ``world.apps``
        relies on for its cross-app registration hooks.
        """
        from evennia_extensions.typeclass_hook_guard import (  # noqa: PLC0415
            install_lifecycle_hook_guards,
        )

        install_lifecycle_hook_guards()

        from evennia_extensions import checks  # noqa: F401, PLC0415  (registers the system check)
