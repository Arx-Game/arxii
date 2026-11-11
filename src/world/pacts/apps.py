"""Startup hook for being pacts (#4341), called from world/apps.py."""


def ready() -> None:
    """Register pact-side hooks at startup.

    Empty for now: the pact services task registers the PACT_PERIOD project kind's
    tiered resolver here, the way ``world.worship.apps`` registers PLEDGE.
    """
