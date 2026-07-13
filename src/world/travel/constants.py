"""Constants for the overworld travel system (#1855)."""

from django.db import models


class TravelMode(models.TextChoices):
    """Mode of travel — determines which routes a method can use."""

    LAND = "LAND", "Land"
    SEA = "SEA", "Sea"
    AIR = "AIR", "Air"


class VoyageStatus(models.TextChoices):
    """Status of a voyage."""

    IN_TRANSIT = "IN_TRANSIT", "In Transit"
    ARRIVED = "ARRIVED", "Arrived"
    ABANDONED = "ABANDONED", "Abandoned"
