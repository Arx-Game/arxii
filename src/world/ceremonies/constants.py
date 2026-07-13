"""Constants for the ceremonies framework (#2289)."""

from django.db import models


class CeremonyStatus(models.TextChoices):
    OPEN = "open", "Open"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class CeremonyTypeKey(models.TextChoices):
    """Handler discriminator for ceremony types.

    FUNERAL carries the full handler (dead honorees, ghost container, will seam);
    BLESSING and SERMON are renown/resonance-only. Wedding/Coronation arrive as
    new keys + handlers later (#2358).
    """

    FUNERAL = "funeral", "Funeral"
    BLESSING = "blessing", "Blessing"
    SERMON = "sermon", "Sermon"
