from django.db import models


class NarrativeCategory(models.TextChoices):
    STORY = "story", "Story update"
    ATMOSPHERE = "atmosphere", "Atmosphere"
    VISIONS = "visions", "Visions"
    HAPPENSTANCE = "happenstance", "Happenstance"
    SYSTEM = "system", "System"
    COVENANT = "covenant", "Covenant"
    RENOWN = "renown", "Renown"


class GemitReach(models.TextChoices):
    """How wide a gemit broadcasts (#1450) — its audience scope.

    GAME_WIDE reaches every online session (the classic gemit). SOCIETY / ORGANIZATION reach only
    the members of the linked societies / organizations (multiple targets allowed per gemit).
    """

    GAME_WIDE = "game_wide", "Game-wide"
    SOCIETY = "society", "Society"
    ORGANIZATION = "organization", "Organization"
