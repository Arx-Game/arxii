from django.db import models


class ResponseType(models.TextChoices):
    """Type of journal response."""

    PRAISE = "praise", "Praise"
    RETORT = "retort", "Retort"


class PosthumousOverride(models.TextChoices):
    """Per-entry override of the author's ``CharacterSheet.posthumous_journal_disposition``.

    INHERIT (default) falls through to the sheet-level default; REVEAL/SEAL pin this one
    entry regardless of the sheet default. SEAL always wins — a sealed entry is readable by
    no one, ever, including a bequest recipient (#3287 Decision 3).
    """

    INHERIT = "inherit", "Inherit sheet default"
    REVEAL = "reveal", "Reveal after death"
    SEAL = "seal", "Seal forever"


# Weekly XP awards for journal actions
JOURNAL_POST_XP = [5, 2, 1]  # 1st, 2nd, 3rd post per week
PRAISE_GIVEN_XP = 2
PRAISE_RECEIVED_XP = 1
RETORT_GIVEN_XP = 1
RETORT_RECEIVED_XP = 3
