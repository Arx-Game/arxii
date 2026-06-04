"""Constants for the NPC services framework."""

from django.db import models


class OfferKind(models.TextChoices):
    """Discriminator for the per-kind details model + effect handler."""

    PERMIT = "permit", "Permit"
    MISSION = "mission", "Mission"
    # Future kinds: loans/training/favors/marriage/attunement.


class DrawMode(models.TextChoices):
    """How offers on a role are surfaced to the player."""

    MENU = "menu", "Menu"  # Deterministic — every eligible offer is shown.
    POOL = "pool", "Pool"  # NPC draws a subset per visit (mission-style; #686).
