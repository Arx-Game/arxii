from django.db import models


class ResponseType(models.TextChoices):
    """Type of journal response.

    PRAISE and CONDEMN are the agree/disagree pair on an entry's substance; RETORT answers
    it. RETORT and CONDEMN are consent-gated (#3941, ADR-0303): offered only to a rival or
    when the writer's ``CharacterSheet.retort_consent`` is ANYONE.
    """

    PRAISE = "praise", "Praise"
    RETORT = "retort", "Retort"
    CONDEMN = "condemn", "Condemn"


class JournalKind(models.TextChoices):
    """What an entry is: an ordinary entry, or one of the CG Introductions (#3621).

    The Introductions are white journals written at character generation (or later, from
    the journals page) whose kind lets the sheet and an institution find them.
    """

    ENTRY = "entry", "Entry"
    FIRST_JOURNAL = "first_journal", "First Journal"
    APPLICATION = "application", "Application to Shroudwatch Academy"
    WHISPERS = "whispers", "The Whispers"


#: The CG Introductions (#3621) as one Search filter ("Introductions", #3941).
INTRODUCTION_KINDS: tuple[str, ...] = (
    JournalKind.FIRST_JOURNAL,
    JournalKind.APPLICATION,
    JournalKind.WHISPERS,
)


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
CONDEMN_GIVEN_XP = RETORT_GIVEN_XP
CONDEMN_RECEIVED_XP = RETORT_RECEIVED_XP
