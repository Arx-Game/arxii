"""Felt moon pull (#2845) — the graded read behind lycan control checks.

The instinctual sibling of ``felt_sun_exposure``, deliberately simpler: the
pull is about what reaches the sky-exposed character, so mundane clothing and
modifier magic never enter it — only real occlusion (roof, shade, cloud
cover) dampens the moon:

    pull = max(0, base(illumination, NIGHT, sky) - shade)

Cloud cover needs no moon-side code: weather materializes area-wide shelter
rows on the radiant damage-type axis (ADR-0180), and the same read that
shades the sun shades the moon.
"""

from __future__ import annotations

from typing import NamedTuple

from world.game_clock.constants import TimePhase
from world.game_clock.services import get_ic_phase, get_moon_illumination
from world.species.moon_constants import BASE_MOON_FULL, MOON_FORM_CLARITY_MAX_BONUS
from world.species.sun_exposure import _shade_value, _sky_exposed


class MoonPull(NamedTuple):
    """Component breakdown of the moon's felt pull on one character in one room."""

    base: int
    shade: int
    pull: int


_NO_PULL = MoonPull(0, 0, 0)


def felt_moon_pull(character, room) -> MoonPull:
    """Compute *character*'s felt moon pull in *room* with full breakdown."""
    base = _base_moonlight(room)
    if base <= 0:
        return _NO_PULL
    shade = _shade_value(character, room)
    return MoonPull(base=base, shade=shade, pull=max(0, base - shade))


def _base_moonlight(room) -> int:
    """Moonlight reaching *room*'s occupants before shade — NIGHT only."""
    if not _sky_exposed(room):
        return 0
    if get_ic_phase() != TimePhase.NIGHT:
        return 0
    illumination = get_moon_illumination()
    if illumination is None:
        return 0
    return round(illumination * BASE_MOON_FULL)


def moon_clarity_instance_value(character, room) -> float:
    """The battle-form ``instance_value`` multiplier for a shift here and now.

    1.0 baseline (day, indoors, new moon); rises linearly with the felt pull
    to ``1.0 + MOON_FORM_CLARITY_MAX_BONUS`` under a clear full moon. Applies
    to voluntary and forced shifts alike — the moon empowers the form
    regardless of who chose the shift (ruled 2026-07-31).
    """
    exposure = felt_moon_pull(character, room)
    if exposure.pull <= 0:
        return 1.0
    fraction = min(1.0, exposure.pull / BASE_MOON_FULL)
    return 1.0 + fraction * MOON_FORM_CLARITY_MAX_BONUS
