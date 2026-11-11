"""Startup hook for being pacts (#4341), called from world/apps.py."""


def ready() -> None:
    """Register the PACT_PERIOD project kind: its tiered resolver and kind handler.

    The resolver picks the period's tier (met or short) at its time limit and
    ``resolve_project`` runs the handler, which grades it once.
    """
    from world.pacts.services import grade_pact_period, resolve_pact_period  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import (  # noqa: PLC0415
        register_kind_handler,
        register_tiered_resolver,
    )

    register_kind_handler(ProjectKind.PACT_PERIOD, grade_pact_period)
    register_tiered_resolver(ProjectKind.PACT_PERIOD, resolve_pact_period)
