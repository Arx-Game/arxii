"""Shared enums for evennia_extensions models."""

from __future__ import annotations

from django.db import models


class RoomEnclosure(models.TextChoices):
    """How enclosed a room is — gates which outdoor weather reaches its inhabitants (#1514).

    A finer-grained companion to ``RoomProfile.is_outdoor`` (which stays as the coarse
    weather-writes/permit flag). Enclosure shelters the *weather* exposure axes (rain/snow,
    wind); *temperature* (COLD/HEAT) seeps through regardless and is countered by
    fixtures/style, not enclosure. Which axes each level shelters lives in
    ``world.locations.constants.ENCLOSURE_SHELTERED_AXES``.
    """

    OPEN_AIR = "open_air", "Open-air"  # exposed to all weather (a veranda with no roof)
    ROOFED = "roofed", "Roofed"  # a roof stops rain/snow, but wind still reaches you
    WALLED = "walled", "Walled"  # roof + walls stop rain/snow and wind
    SEALED = "sealed", "Sealed"  # fully enclosed; also the substrate for future insulation
