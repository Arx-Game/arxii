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

    GAME_WIDE reaches every online session (the classic gemit). SPECIFIED reaches the members of any
    combination of the linked societies and/or organizations — the two are not mutually exclusive,
    so one gemit can target a House (org) and a Society together.
    """

    GAME_WIDE = "game_wide", "Game-wide"
    SPECIFIED = "specified", "Specified"
