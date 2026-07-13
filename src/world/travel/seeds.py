"""Seed content for the overworld travel system (#1855).

Starter content: "On Foot" + "Sailing Ship" travel methods.

Run via:
    uv run arx shell -c "from world.travel.seeds import \
        ensure_travel_content; ensure_travel_content()"
"""

from world.travel.constants import TravelMode
from world.travel.models import TravelHub, TravelMethod, TravelRoute


def ensure_travel_content():
    """Create starter travel content if it doesn't exist."""
    TravelMethod.objects.get_or_create(
        name="On Foot",
        defaults={
            "travel_mode": TravelMode.LAND,
            "base_speed": 5.0,
            "is_default": True,
            "description": "Walking. Slow but reliable.",
        },
    )

    TravelMethod.objects.get_or_create(
        name="Sailing Ship",
        defaults={
            "travel_mode": TravelMode.SEA,
            "base_speed": 15.0,
            "is_default": False,
            "description": "A sailing vessel. Faster than walking, but requires a ship.",
        },
    )

    print(f"Travel methods: {TravelMethod.objects.count()} rows")
    print(f"Travel hubs: {TravelHub.objects.count()} rows")
    print(f"Travel routes: {TravelRoute.objects.count()} rows")
    print("Travel content seed complete.")
