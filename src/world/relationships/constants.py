"""Constants for the relationships app (#3957: ties, labels, depth, tiers)."""

from django.db import models

# Points applied per ambient relationship bump — rel plus/neg, valenced emoji reactions (#1699).
BUMP_POINTS = 1


class BumpValence(models.IntegerChoices):
    """Direction of an ambient relationship bump (#1699)."""

    POSITIVE = 1, "Positive"
    NEGATIVE = -1, "Negative"


class TypeValence(models.TextChoices):
    """Whether a label type reads as warm, hostile or neither (#3957).

    Hostile-valence labels are the ones consent's RIVALS mode and the journals' Retort
    gate read; the surge engine's hated-foe leg reads them too.
    """

    WARM = "warm", "Warm"
    HOSTILE = "hostile", "Hostile"
    NEUTRAL = "neutral", "Neutral"


class TypeFamily(models.TextChoices):
    """How the picker groups the catalogue (#3957). Purely presentational."""

    HEART = "heart", "Heart"
    COMPANY = "company", "Company"
    CONTEST = "contest", "Contest"
    BLOOD_AND_OATH = "blood_and_oath", "Blood and oath"
    TEACHING = "teaching", "Teaching"


class LabelAwareness(models.TextChoices):
    """Who knows a label exists (#3957). Moves forward only; see ``advance_awareness``."""

    PRIVATE = "private", "Private"
    CLANDESTINE = "clandestine", "Clandestine"
    PUBLIC = "public", "Public"


#: The one-way order: a label may only move to a HIGHER rank.
AWARENESS_RANK: dict[str, int] = {
    LabelAwareness.PRIVATE: 0,
    LabelAwareness.CLANDESTINE: 1,
    LabelAwareness.PUBLIC: 2,
}

#: Awareness stages the OTHER side may see (and the only ones that count toward mutual).
KNOWN_AWARENESS: tuple[str, ...] = (LabelAwareness.CLANDESTINE, LabelAwareness.PUBLIC)


class DepthSource(models.TextChoices):
    """Where a depth award came from (#3957) — the audit row's provenance."""

    ALLOCATION = "allocation", "Weekly allocation"
    SCENE = "scene", "Scene together"


class TieAudience(models.TextChoices):
    """Who is looking at a side of a tie (#3957); decides which fields a read emits."""

    OWNER = "owner", "Owner"
    OTHER_SIDE = "other_side", "Other side"
    THIRD_PARTY = "third_party", "Third party"
    STAFF = "staff", "Staff"
