def ready() -> None:
    """Register the RESEARCH project-kind resolver (#1146).

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.clues`` stops being its own installed app.
    """
    # Register the RESEARCH project-kind resolver with the projects framework
    # (#1146) — the same app-ready handshake buildings use for construction.
    from world.clues.research import resolve_research  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import register_kind_handler  # noqa: PLC0415

    register_kind_handler(ProjectKind.RESEARCH, resolve_research)
