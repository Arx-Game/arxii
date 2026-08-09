"""``world.gm`` app-ready hook — registers cross-app handlers (#3071)."""


def ready() -> None:
    """Register the GM summon offer handler for telnet accept/decline routing.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly. No prior claim on
    the ``"summon"`` keyword exists in ``commands.offer_registry`` — this is a
    fresh registration, not a replacement, so it is safe appended at the end of
    the aggregator's call order.
    """
    from commands.offer_registry import register_offer_handler  # noqa: PLC0415
    from world.gm.offer_handlers import GMSummonPendingHandler  # noqa: PLC0415

    register_offer_handler(GMSummonPendingHandler())
