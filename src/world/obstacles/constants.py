"""Constants and enums for the obstacles system."""

from django.db import models


class DiscoveryType(models.TextChoices):
    """Whether a bypass option is immediately visible or must be discovered."""

    OBVIOUS = "obvious", "Obvious (visible if capability met)"
    DISCOVERABLE = "discoverable", "Discoverable (must be learned)"


class ResolutionType(models.TextChoices):
    """What happens to an obstacle when bypassed."""

    DESTROY = "destroy", "Destroy (removed for everyone)"
    PERSONAL = "personal", "Personal (bypassed for this character only)"
    TEMPORARY = "temporary", "Temporary (suppressed for N rounds)"
