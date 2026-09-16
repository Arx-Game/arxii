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


class BeingResonanceTier(models.TextChoices):
    """How strongly a being favors a resonance (#3776).

    FAVORED acts done in the being's name pay 2x; ASSOCIATED pays 1x.
    """

    FAVORED = "favored", "Favored"
    ASSOCIATED = "associated", "Associated"


class BeingRelationshipValence(models.TextChoices):
    """The public-facing nature of a relationship between two beings (#3776)."""

    ALLY = "ally", "Ally"
    RIVAL = "rival", "Rival"
    FEUD = "feud", "Feud"
    UNKNOWN = "unknown", "Unclear"


class RiteTier(models.IntegerChoices):
    """How demanding a worship rite is (#3777). The tier lives on the RiteKind
    and sets everything mechanical: the AP cost (1 AP per tier), the award table
    row (WorshipRiteTierAward keyed on tier + outcome) and, at tier 3, that the
    rite is a full Ceremony rather than a solo act."""

    DEVOTIONAL = 1, "Devotional"
    DEMANDING = 2, "Demanding"
    PERILOUS = 3, "Perilous"


# PLACEHOLDER magnitudes for worship rites (#3777); every one is a first guess.
# A rite costs one Action Point per tier and a little social fatigue.
RITE_AP_COST_PER_TIER = 1
RITE_SOCIAL_FATIGUE_COST = 1
# Reward multipliers, in percent, applied to a rite's tier award. They stack by
# multiplication when more than one holds.
FAVORED_RESONANCE_REWARD_MULTIPLIER_PERCENT = 200  # BeingResonance.tier == FAVORED
FEAST_DAY_REWARD_MULTIPLIER_PERCENT = 200  # performed on one of the being's feast days
BIRTH_FAVOR_REWARD_MULTIPLIER_PERCENT = 200  # is_birth_favored_by holds today
