"""Constants for the GM system."""

from django.db import models


class GMLevel(models.TextChoices):
    """GM trust/permission tiers. Higher levels unlock broader story scope and reward caps."""

    STARTING = "starting", "Starting GM"
    JUNIOR = "junior", "Junior GM"
    GM = "gm", "GM"
    EXPERIENCED = "experienced", "Experienced GM"
    SENIOR = "senior", "Senior GM"


class GMApplicationStatus(models.TextChoices):
    """Status for GM applications."""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"
