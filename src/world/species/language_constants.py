"""Fluency vocabulary for language traits (#2993).

Band thresholds are PLACEHOLDER tuning values (Apostate's ratified defaults):
1-29 broken, 30-69 conversational, 70+ fluent. The raw 1-100 value drives
progression (DevelopmentPoints); the band drives comprehension rendering.
"""

from enum import Enum

BROKEN_MAX = 29
CONVERSATIONAL_MAX = 69
FLUENT_GRANT_VALUE = 70


class Fluency(Enum):
    NONE = "none"
    BROKEN = "broken"
    CONVERSATIONAL = "conversational"
    FLUENT = "fluent"


# Comprehension keep-ratios per band (fraction of words that survive garbling).
BAND_KEEP_RATIO: dict[Fluency, float] = {
    Fluency.NONE: 0.0,
    Fluency.BROKEN: 1 / 6,
    Fluency.CONVERSATIONAL: 1 / 2,
    Fluency.FLUENT: 1.0,
}


def fluency_band(value: int) -> Fluency:
    """The comprehension band for a 1-100 fluency value (0/absent = NONE)."""
    if value <= 0:
        return Fluency.NONE
    if value <= BROKEN_MAX:
        return Fluency.BROKEN
    if value <= CONVERSATIONAL_MAX:
        return Fluency.CONVERSATIONAL
    return Fluency.FLUENT
