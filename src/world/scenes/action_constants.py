"""Constants for scene action requests."""

from itertools import pairwise

from django.db import models


class ActionRequestStatus(models.TextChoices):
    """Status of a scene action request."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DENIED = "denied", "Denied"
    RESOLVED = "resolved", "Resolved"
    EXPIRED = "expired", "Expired"


class DifficultyChoice(models.TextChoices):
    """Difficulty level for scene action checks."""

    TRIVIAL = "trivial", "Trivial"
    EASY = "easy", "Easy"
    NORMAL = "normal", "Normal"
    HARD = "hard", "Hard"
    DAUNTING = "daunting", "Daunting"
    HARROWING = "harrowing", "Harrowing"


class ConsentDecision(models.TextChoices):
    """Player consent decision for an action targeting them."""

    ACCEPT = "accept", "Accept"
    DENY = "deny", "Deny"


class ActionDelivery(models.TextChoices):
    """Audience routing for a scene action's result echo (#903).

    NOT a fork of InteractionMode: delivery is a routing strategy that maps
    onto (mode, receivers, place) at interaction-creation time. TABLE_TALK
    has no mode of its own — it is place-scoping. MUTTER (#905) is the
    partial echo: receivers get the full text, the room gets a random-word
    fragment (two interactions — the fragment is public BECAUSE it is what
    the room heard). EMIT (pemit GM surface) lives on the staff action.
    """

    POSE = "pose", "Pose (whole room)"
    WHISPER = "whisper", "Whisper (target only)"
    TABLE_TALK = "table_talk", "Table talk (your place)"
    MUTTER = "mutter", "Mutter (partial echo)"


DIFFICULTY_VALUES: dict[str, int] = {
    DifficultyChoice.TRIVIAL: 15,
    DifficultyChoice.EASY: 30,
    DifficultyChoice.NORMAL: 45,
    DifficultyChoice.HARD: 60,
    DifficultyChoice.DAUNTING: 75,
    DifficultyChoice.HARROWING: 90,
}

#: Points between two adjacent difficulty bands (#2865). Derived from the table
#: above rather than re-typed as a literal, so re-tuning the bands can never
#: leave a stale step behind. The bands are evenly spaced by construction; the
#: assertion pins that so a future uneven table fails loudly at import instead of
#: silently making "one band harder" mean different things at different bands.
_DIFFICULTY_POINTS: tuple[int, ...] = tuple(DIFFICULTY_VALUES.values())
DIFFICULTY_BAND_STEP: int = _DIFFICULTY_POINTS[1] - _DIFFICULTY_POINTS[0]
assert all(  # noqa: S101 -- import-time invariant on an authored constant table
    hi - lo == DIFFICULTY_BAND_STEP for lo, hi in pairwise(_DIFFICULTY_POINTS)
), "DIFFICULTY_VALUES bands must stay evenly spaced for DIFFICULTY_BAND_STEP to be meaningful."

#: Lowest and highest authored difficulty in points — the bounds a per-instance
#: severity adjustment may not shift a challenge past (refuse, never clamp).
MIN_DIFFICULTY_POINTS: int = _DIFFICULTY_POINTS[0]
MAX_DIFFICULTY_POINTS: int = _DIFFICULTY_POINTS[-1]


class CastPullTier(models.IntegerChoices):
    """Paid pull tiers declarable alongside a standalone cast (#854)."""

    TIER_1 = 1, "Tier 1"
    TIER_2 = 2, "Tier 2"
    TIER_3 = 3, "Tier 3"


CAST_ACTION_KEY = "cast"  # sentinel marking a standalone cast request

# Base social-fatigue cost charged to a defender who actively resists a social action.
# The actual cost is scaled by the resist_effort multiplier in apply_fatigue — tunable.
RESIST_FATIGUE_BASE = 1

# Authored difficulty bands keyed by technique intensity ceiling. Single source
# of truth (no inline magic numbers in logic). On the same 0-75 scale as
# DIFFICULTY_VALUES so consequence resolution thresholds line up.
CAST_DIFFICULTY_BANDS: tuple[tuple[int, int], ...] = (
    (2, 15),
    (4, 30),
    (6, 45),
    (8, 60),
    (9999, 75),
)


class BoonKind(models.TextChoices):
    """What a Boon asks for (#2540). All five kinds fulfill (see boon_services.py)."""

    MONEY = "money", "Money"
    HELD_ITEM = "held_item", "A held item"  # a named item the target currently carries
    VAULT_ITEM = "vault_item", "A vault item"  # from the org vault, via its audited withdraw
    DEED = "deed", "A deed"  # do a thing — RP, no mechanical transfer
    MATERIAL = "material", "Material"  # a bulk material bucket (#2540 slice 3)


class BoonSumTier(models.TextChoices):
    """How big a MONEY boon is *to the target* (#2540 ruling 2026-07-20).

    Money asks never name raw coppers — the asker picks a relative sum and the
    concrete value derives from the target's purse at ask time (displayed to the
    asker; the OOC reveal is accepted). Kills the purse-probe vector at the root:
    there is no arbitrary amount to binary-search with.
    """

    MINOR = "minor", "A minor sum"
    FAIR = "fair", "A fair sum"
    GREAT = "great", "A great sum"
