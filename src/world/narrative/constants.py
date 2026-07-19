from django.db import models


class NarrativeCategory(models.TextChoices):
    STORY = "story", "Story update"
    ATMOSPHERE = "atmosphere", "Atmosphere"
    VISIONS = "visions", "Visions"
    HAPPENSTANCE = "happenstance", "Happenstance"
    SYSTEM = "system", "System"
    COVENANT = "covenant", "Covenant"
    RENOWN = "renown", "Renown"
    WEATHER = "weather", "Weather"
    ABILITY = "ability", "Ability access"


class GemitReach(models.TextChoices):
    """How wide a gemit broadcasts (#1450) — its audience scope.

    GAME_WIDE reaches every online session (the classic gemit). SPECIFIED reaches the members of any
    combination of the linked societies and/or organizations — the two are not mutually exclusive,
    so one gemit can target a House (org) and a Society together.
    """

    GAME_WIDE = "game_wide", "Game-wide"
    SPECIFIED = "specified", "Specified"


class AmbientTriggerType(models.TextChoices):
    """Which condition (if any) gates an AmbientEmoteLine (#2471).

    NONE is the plain, unconditional "atmosphere" case (private to the arriver).
    Every other value is a category-based condition on the arriving character —
    never a specific named character (a per-character "legend callout" reaction
    is a deferred, separate feature — see the #2471 spec's Scope / follow-ups).
    """

    NONE = "none", "Unconditional (plain atmosphere)"
    SPECIES = "species", "Species"
    RESONANCE_MIN = "resonance_min", "Resonance threshold"
    DISTINCTION = "distinction", "Distinction"
    RENOWN_MIN = "renown_min", "Fame tier"
