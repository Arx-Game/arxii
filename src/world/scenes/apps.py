def ready() -> None:
    """Register the boon scene-action resolver.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.scenes`` stops being its own installed app.
    """
    # Import for the register_resolver("boon", ...) side effect (#2540) — the
    # same pattern societies uses for spread_services.
    from world.scenes import boon_services  # noqa: F401, PLC0415
