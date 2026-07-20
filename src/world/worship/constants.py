"""Constants for the worship foundation (#2355) and miracles (#2360)."""

from django.db import models

#: Achievement names for the top-devotion worshipper of a being (Decision 6, #2355).
#: Three gendered display variants; selection maps from CharacterSheet.gender.key.
GODS_FAVORITE_PRINCESS = "God's Favorite Princess"
GODS_FAVORITE_PRINCE = "God's Favorite Prince"
GODS_FAVORITE_CHOSEN = "God's Favorite Chosen"

#: Default Secret level for a CG-minted secret worship (PLACEHOLDER magnitude).
WORSHIP_SECRET_DEFAULT_LEVEL = 2


class MiracleTrigger(models.TextChoices):
    """Danger context a miracle responds to (#2360).

    Only ``INCAPACITATED`` is wired in this issue; ``NEAR_DEATH`` is
    defined for future use (see Scope/follow-ups in the spec).
    """

    INCAPACITATED = "incapacitated", "Character Incapacitated"
    NEAR_DEATH = "near_death", "Character Near Death"
