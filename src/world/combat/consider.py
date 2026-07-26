"""Narrative /consider — band computation, skew logic, and prose assembly (#2716).

This module holds the pure functions for mapping a level gap to a banded
prose index, applying failure skew, and rendering health bands. The
``consider_opponent`` service function calls these.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

# --- Band definitions ---------------------------------------------------------
# Each band is (min_gap, max_gap, prose). Gaps are opponent_level - player_level.
# Coarse bands: 5 entries (ungated players). Fine bands: 9 entries (enhanced).

COARSE_BANDS: list[tuple[int, int, str]] = [
    (-(10**9), -5, "far below you"),
    (-4, -2, "below you"),
    (-1, 1, "an even match"),
    (2, 4, "above you"),
    (5, 10**9, "far above you"),
]

FINE_BANDS: list[tuple[int, int, str]] = [
    (-(10**9), -10, "beneath your notice"),
    (-9, -5, "far below you"),
    (-4, -3, "below you"),
    (-2, -2, "somewhat below you"),
    (-1, 1, "an even match"),
    (2, 2, "somewhat above you"),
    (3, 4, "above you"),
    (5, 9, "far above you"),
    (10, 10**9, "beyond your reckoning"),
]


def gap_to_band_index(gap: int, *, fine: bool = False) -> int:
    """Map a level gap to a band index.

    Args:
        gap: opponent_level - player_level.
        fine: True for the 9-band fine set, False for the 5-band coarse set.

    Returns:
        Band index (0 = lowest, len(bands)-1 = highest).
    """
    bands = FINE_BANDS if fine else COARSE_BANDS
    for index, (min_gap, max_gap, _prose) in enumerate(bands):
        if min_gap <= gap <= max_gap:
            return index
    # Should be unreachable — the first/last bands span ±infinity.
    return 0 if gap < 0 else len(bands) - 1


def band_prose(index: int, *, fine: bool = False) -> str:
    """Return the prose string for a band index."""
    bands = FINE_BANDS if fine else COARSE_BANDS
    return bands[index][2]


# --- Skew logic ---------------------------------------------------------------


# --- Skew thresholds ---------------------------------------------------------
# Success-level boundaries that determine skew magnitude.
_SKEW_PRECISE_FLOOR = 1  # >= 1: accurate (skew 0)
_SKEW_MISTAKEN_FLOOR = -4  # >= -4: off by 1
_SKEW_WILDLY_WRONG_FLOOR = -9  # >= -9: off by 2
# < -9: off by 3 (crit fail)

# Health percentage thresholds for health_band prose.
_HEALTH_HALE = 75
_HEALTH_WOUNDED = 50
_HEALTH_BLOODIED = 25


def skew_for_success_level(success_level: int) -> int:
    """Return the skew magnitude for a given check success level.

    Args:
        success_level: The check's success_level (-10 to +10).

    Returns:
        0 (accurate), 1 (mistaken), 2 (wildly wrong), or 3 (crit fail).
    """
    if success_level >= _SKEW_PRECISE_FLOOR:
        return 0
    if success_level >= _SKEW_MISTAKEN_FLOOR:
        return 1
    if success_level >= _SKEW_WILDLY_WRONG_FLOOR:
        return 2
    return 3


def bias_direction(true_index: int, skew: int, character: ObjectDB | None) -> int:  # noqa: ARG001
    """Return +1 or -1 — the direction to skew the reported band.

    ``character`` is the ObjectDB resolved from
    ``participant.character_sheet.character``.

    Default: random.choice([-1, +1]).
    Override point for the future Overconfident distinction, which
    always returns -1 (toward 'weaker than you actually are').

    Args:
        true_index: The correct band index.
        skew: The skew magnitude (from ``skew_for_success_level``).
        character: The assessing character (for future distinction lookup).

    Returns:
        +1, -1, or 0 (when skew is 0).
    """
    if skew == 0:
        return 0
    return random.choice([-1, 1])  # noqa: S311


def apply_skew(
    true_index: int,
    skew: int,
    character: ObjectDB | None,
    *,
    max_index: int,
) -> int:
    """Apply directional skew to a band index, clamped to valid range.

    Args:
        true_index: The correct band index.
        skew: The skew magnitude.
        character: The assessing character.
        max_index: The maximum valid band index (len(bands) - 1).

    Returns:
        The reported (possibly wrong) band index, clamped to [0, max_index].
    """
    direction = bias_direction(true_index, skew, character)
    reported = true_index + direction * skew
    return max(0, min(reported, max_index))


# --- Health band --------------------------------------------------------------


def health_band(health: int, max_health: int) -> str:
    """Return narrative prose for an opponent's health percentage.

    Args:
        health: Current health.
        max_health: Maximum health.

    Returns:
        One of: "hale and unwounded", "wounded but standing",
        "bloodied and flagging", "on the verge of collapse".
    """
    if max_health <= 0:
        return "on the verge of collapse"
    pct = (health / max_health) * 100
    if pct >= _HEALTH_HALE:
        return "hale and unwounded"
    if pct >= _HEALTH_WOUNDED:
        return "wounded but standing"
    if pct >= _HEALTH_BLOODIED:
        return "bloodied and flagging"
    return "on the verge of collapse"
