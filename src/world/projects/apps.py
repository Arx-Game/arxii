"""Startup hook for the projects framework, called from world/apps.py."""


def ready() -> None:
    """App ready - no DB queries at import time.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.projects`` stops being its own installed app.
    """
