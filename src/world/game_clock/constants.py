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
