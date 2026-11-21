"""Constants for the game clock system."""

from django.db.models import TextChoices


class TimePhase(TextChoices):
    """Time-of-day phases with season-adjusted boundaries."""

    DAWN = "dawn", "Dawn"
    DAY = "day", "Day"
    DUSK = "dusk", "Dusk"
    NIGHT = "night", "Night"


class Season(TextChoices):
    """IC calendar seasons derived from month."""

    SPRING = "spring", "Spring"
    SUMMER = "summer", "Summer"
    AUTUMN = "autumn", "Autumn"
    WINTER = "winter", "Winter"


# Default time ratio: 3 IC seconds per 1 real second
DEFAULT_TIME_RATIO = 3.0

# Season-adjusted phase boundaries (IC hour)
# Each season defines (dawn_start, day_start, dusk_start, night_start)
PHASE_BOUNDARIES: dict[Season, tuple[float, float, float, float]] = {
    Season.SPRING: (5.5, 6.5, 18.5, 19.5),
    Season.SUMMER: (4.5, 5.5, 20.0, 21.0),
    Season.AUTUMN: (6.0, 7.0, 17.5, 18.5),
    Season.WINTER: (7.0, 8.0, 16.5, 17.5),
}

# Month-to-season mapping (1-indexed months)
MONTH_TO_SEASON: dict[int, Season] = {
    1: Season.WINTER,
    2: Season.WINTER,
    3: Season.SPRING,
    4: Season.SPRING,
    5: Season.SPRING,
    6: Season.SUMMER,
    7: Season.SUMMER,
    8: Season.SUMMER,
    9: Season.AUTUMN,
    10: Season.AUTUMN,
    11: Season.AUTUMN,
    12: Season.WINTER,
}

# IC month names (#4185), 1:1 with Gregorian months, so IC dates stay plain
# datetimes and seasons/moons are unaffected. Each reads as "the Month of ___".
IC_MONTH_NAMES: dict[int, str] = {
    1: "Dreaming",
    2: "Choosing",
    3: "Thawing",
    4: "Waking",
    5: "Rising",
    6: "Vowing",
    7: "Enduring",
    8: "Gathering",
    9: "Unyielding",
    10: "Masquing",
    11: "Keeping",
    12: "Ending",
}


class MoonPhase(TextChoices):
    """Lunar phases derived from IC time (#2845 celestial layer).

    Deterministic off the IC clock — no state, no cron writer: every read
    tracks the synodic cycle as time advances (staff time-skips included).
    """

    NEW = "new", "New Moon"
    WAXING_CRESCENT = "waxing_crescent", "Waxing Crescent"
    FIRST_QUARTER = "first_quarter", "First Quarter"
    WAXING_GIBBOUS = "waxing_gibbous", "Waxing Gibbous"
    FULL = "full", "Full Moon"
    WANING_GIBBOUS = "waning_gibbous", "Waning Gibbous"
    LAST_QUARTER = "last_quarter", "Last Quarter"
    WANING_CRESCENT = "waning_crescent", "Waning Crescent"


# PLACEHOLDER tuning (#2845): synodic cycle length in IC days, and the fixed IC
# epoch anchoring a NEW moon. 30 IC days ≈ one IC month per cycle.
MOON_SYNODIC_IC_DAYS = 30.0


#: The years the clock may be set to (#5248). The calendar is Python's, which ends at
#: year 9999 and begins at year 1; the clock keeps running after it is set, and a jump
#: moves other stored dates by its length, so the ends are kept well clear. A running
#: clock that reached year 9999 would raise on every read of the time.
MIN_CLOCK_YEAR = 100
MAX_CLOCK_YEAR = 9000


class AgeHandling(TextChoices):
    """What a change of the clock's date does to characters' ages (#5248).

    ``AGED``: the calendar moves under the characters. Birth years stay, so every
    chronological age changes by the years jumped, and the birthday task matures each
    character by the birthdays skipped. ``KEPT``: the calendar moves and the characters
    move with it. Every birth year shifts by the years jumped, so nobody's age changes.
    A change to an earlier date is always ``KEPT``: maturation is recorded and does not
    go down, so a calendar cannot make anyone younger.
    """

    AGED = "aged", "Characters age"
    KEPT = "kept", "Characters keep their ages"


class ClockChange(TextChoices):
    """The kind of change one ``GameClockHistory`` row records (#5248).

    The row's anchors and ratios cannot tell a pause from a change of date, so the kind
    is stored. Rows written before #5248 carry a blank.
    """

    PAUSED = "paused", "Paused"
    RESUMED = "resumed", "Resumed"
    SPEED = "speed", "Speed changed"
    DATE_AGED = "date_aged", "Date set, characters aged"
    DATE_KEPT = "date_kept", "Date set, characters kept their ages"


class JumpDirection(TextChoices):
    """Which way a change of the clock's date moves the calendar (#5248)."""

    FORWARD = "forward", "Forward"
    BACK = "back", "Back"
    NONE = "none", "No change"
