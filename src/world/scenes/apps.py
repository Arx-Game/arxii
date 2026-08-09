def ready() -> None:
    """Register the boon scene-action resolver.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.scenes`` stops being its own installed app.
    """
    # Import for the register_resolver("boon", ...) side effect (#2540) — the
    # same pattern societies uses for spread_services. Also imports the offer-registry
    # registration for #3069's `accept precapture` / `decline precapture` routing.
    from commands.offer_registry import register_offer_handler  # noqa: PLC0415
    from world.scenes import boon_services  # noqa: F401, PLC0415
    from world.scenes.precapture_offer_handler import (  # noqa: PLC0415
        PrecaptureConsentOfferHandler,
    )

    register_offer_handler(PrecaptureConsentOfferHandler())
