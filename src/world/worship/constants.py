"""Constants for the worship foundation (#2355) and miracles (#2360)."""

from django.db import models

from world.magic.constants import GainSource

#: Achievement names for the top-devotion worshipper of a being (Decision 6, #2355).
#: Three gendered display variants; selection maps from CharacterSheet.gender.key.
GODS_FAVORITE_PRINCESS = "God's Favorite Princess"
GODS_FAVORITE_PRINCE = "God's Favorite Prince"
GODS_FAVORITE_CHOSEN = "God's Favorite Chosen"

#: Default Secret level for a CG-minted secret worship (PLACEHOLDER magnitude).
WORSHIP_SECRET_DEFAULT_LEVEL = 2


class MiracleTrigger(models.TextChoices):
    """Danger context a miracle responds to (#2360).

    ``INCAPACITATED`` fires from the combat trigger (#2360); ``NEAR_DEATH`` is
    the dire-straits prayer's trigger (#3779): a character in Soulfray or below
    the knockout health band prays, and a miracle of that trigger may answer.
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


class ConsecrationScope(models.TextChoices):
    """Which holy site a consecration tier row describes (#3778)."""

    SHRINE = "shrine", "Shrine"
    TEMPLE = "temple", "Temple"


# A rite performed at a holy site of its own being consecrates it by its tier
# in points (#3778). PLACEHOLDER magnitude; the tier tables are authored rows.
CONSECRATION_POINTS_PER_RITE_TIER = 1
SHRINE_KIND_NAME = "Shrine"


class DireStraitsKind(models.TextChoices):
    """Why a prayer counted as dire straits (#3779), recorded on the ``Prayer``."""

    SOULFRAY = "soulfray", "Soulfray active"
    NEAR_DEATH = "near_death", "Near death"


# Freeform prayer (#3779). Every magnitude is PLACEHOLDER.
PRAYER_TEXT_MAX_LENGTH = 2000
PRAYER_SITE_DEVOTION_AMOUNT = 1  # the weekly holy-site prayer, below a tier 1 rite
VISION_RESONANCE_POOL_COST = 10  # what a being spends to send one vision
PRAYER_INTERVENTION_EVENT_PREFIX = "prayer_"  # MiraclePerformance.trigger_event


class BeingVisibility(models.TextChoices):
    """The Deity Editor's read of a being's Codex tier (#3780): PUBLIC when the
    entry is public, OBSCURE when an organization's membership is granted it,
    SECRET when only a Clue reaches it (or no entry exists yet)."""

    PUBLIC = "public", "Public"
    OBSCURE = "obscure", "Obscure"
    SECRET = "secret", "Secret"


# Where the editor files a being's Codex page when it has to create one (#3780).
PANTHEON_CODEX_CATEGORY_NAME = "The World"
PANTHEON_CODEX_SUBJECT_NAME = "The Pantheon"


class FavorAwardKind(models.TextChoices):
    """What a ``FavorOutcomeAward`` row pays (#4333).

    INVOCATION is the bonus, in check points, an invocation check's outcome tier
    adds to the check it was declared on. CLOSING is the base favor a pledge's
    closing rite pays for its outcome tier; pledges read it (#4333 slice 2).
    """

    INVOCATION = "invocation", "Invocation bonus (check points)"
    CLOSING = "closing", "Closing award (base favor)"


#: The longest one-line description a player may attach to an invocation (#4333).
FAVOR_INVOCATION_LINE_MAX_LENGTH = 200
#: The base earning rate, in percent, before the Chosen bonus and favor earning
#: modifiers are added (#4333, design 1a).
FAVOR_EARNING_BASE_PERCENT = 100


class PledgeCreditSource(models.TextChoices):
    """Where one favor credit to a pledge came from (#4333 slice 2).

    Every favor write for a being while the character holds an open pledge to it
    is recorded as a ``PledgeCredit`` with one of these, so the pledge card can
    show each credit with its calculation. CLOSING and LAPSE are the awards paid
    when the pledge resolves; they are recorded but never add to its progress.
    """

    DEED = "deed", "Deed"
    SACRIFICE = "sacrifice", "Sacrifice"
    RITE = "rite", "Rite"
    PRAYER = "prayer", "Holy-site prayer"
    CEREMONY_OFFERING = "ceremony_offering", "Ceremony offering"
    CEREMONY = "ceremony", "Ceremony"
    CLOSING = "closing", "Closing award"
    LAPSE = "lapse", "Lapse award"
    OTHER = "other", "Other"


#: Resonance grant sources with no character action behind them. Favor with a being
#: comes only from a character's actions (owner ruling 2026-10-16), so a grant from
#: one of these earns no pledge deed favor: the daily residence and outfit trickles,
#: a distinction's granted resonance, and a staff grant. A worship rite's own grant
#: is excluded separately (the rite pays its own favor).
PASSIVE_DEED_SOURCES: frozenset[str] = frozenset(
    {
        GainSource.ROOM_RESIDENCE,
        GainSource.OUTFIT_TRICKLE,
        GainSource.DISTINCTION,
        GainSource.STAFF_GRANT,
    }
)


class PledgeState(models.TextChoices):
    """How a character's pledge stands, derived for the pledge card (#4333 slice 2)."""

    OPEN = "open", "Open"
    READY = "ready", "Ready to close"
    CLOSED = "closed", "Closed"
    LAPSED = "lapsed", "Lapsed"


#: Real days in one game week: a pledge's span is its game weeks times this (#4333).
DAYS_PER_GAME_WEEK = 7
#: Closing attempts a pledge allows: a first failure leaves one retry (Ruling 17).
PLEDGE_MAX_CLOSE_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# Answers (#4333 slice 3, design 4)
# ---------------------------------------------------------------------------

#: Lowest outcome success level whose answer may carry fact text and a fact clue (Success).
ANSWER_FACT_MIN_SUCCESS_LEVEL = 1
#: Lowest outcome success level whose answer may carry a follow-up clue (Partial Success).
ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL = 0
#: Longest onlooker line an answer may carry: one room line.
ANSWER_ONLOOKER_LINE_MAX_LENGTH = 300

#: Longest free-text answer a stewarded being's table GM may send (#4333 slice 4).
STEWARD_ANSWER_TEXT_MAX_LENGTH = 4000
