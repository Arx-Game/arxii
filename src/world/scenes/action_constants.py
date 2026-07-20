"""Constants for scene action requests."""

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
    """What a Boon asks for (#2540). MONEY is wired; the rest are follow-up slices."""

    MONEY = "money", "Money"
    HELD_ITEM = "held_item", "A held item"  # a named item the target currently carries
    VAULT_ITEM = "vault_item", "A vault item"  # from the org vault (needs the bank/vault system)
    DEED = "deed", "A deed"  # do a thing — RP, no mechanical transfer
