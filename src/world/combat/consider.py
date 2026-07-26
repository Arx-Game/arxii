"""Narrative /consider — band computation, skew logic, and prose assembly (#2716).

This module holds the pure functions for mapping a level gap to a banded
prose index, applying failure skew, and rendering health bands. The
``consider_opponent`` service function calls these.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from world.traits.constants import PrimaryStat

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.combat.models import CombatOpponent, CombatParticipant, ConsiderReading
    from world.covenants.models import CovenantRole

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


# --- Enhancement detection ----------------------------------------------------


def _role_enhances_assessment(role: CovenantRole) -> bool:
    """True if the role itself enhances assessment, or it rides its parent's flag."""
    if role.enhances_assessment:
        return True
    return role.parent_role_id is not None and role.parent_role.enhances_assessment


def _has_engaged_assessment_role(sheet: CharacterSheet) -> bool:
    """True if the sheet holds an active engaged membership riding enhances_assessment."""
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    memberships = CharacterCovenantRole.objects.filter(
        character_sheet=sheet,
        engaged=True,
        left_at__isnull=True,
    ).select_related("covenant_role", "covenant_role__parent_role")
    return any(_role_enhances_assessment(membership.covenant_role) for membership in memberships)


# --- CheckType get-or-create ---------------------------------------------------

CONSIDER_CHECK_TYPE_NAME = "Consider"


def ensure_consider_check_type() -> CheckType:
    """Get-or-create the 'Consider' CheckType with PERCEPTION as its driving trait.

    No data migration — follows the existing ensure_* pattern (e.g.
    ``src/world/areas/positioning/plummet_content.py:206``).
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import (  # noqa: PLC0415
        CheckCategory,
        CheckType,
        CheckTypeTrait,
    )
    from world.traits.factories import StatTraitFactory  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(name="Exploration")
    check_type, _ = CheckType.objects.get_or_create(
        name=CONSIDER_CHECK_TYPE_NAME,
        category=category,
        defaults={
            "description": "Assess a foe's threat level relative to your own.",
        },
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type,
        trait=StatTraitFactory(
            name=PrimaryStat.PERCEPTION.value,
            category=TraitCategory.META,
        ),
        defaults={"weight": Decimal("1.00")},
    )
    return check_type


# --- Tier prose ---------------------------------------------------------------


def _tier_prose(opponent: CombatOpponent) -> str:
    """Return the authored assess_prose for the opponent's tier, or empty string."""
    from world.combat.models import OpponentTierTemplate  # noqa: PLC0415

    try:
        template = OpponentTierTemplate.objects.get(tier=opponent.tier)
    except OpponentTierTemplate.DoesNotExist:
        return ""
    return template.assess_prose or ""


# --- Main service function ----------------------------------------------------


def consider_opponent(participant: CombatParticipant, opponent: CombatOpponent) -> ConsiderReading:
    """Assess an opponent's threat level and cache the reading.

    Runs a PERCEPTION check opposed by the opponent's level. The success_level
    determines accuracy — failures produce confidently wrong bands. One
    reading per (participant, opponent) is cached; re-calls return the cache.

    Args:
        participant: The assessing CombatParticipant.
        opponent: The CombatOpponent to assess.

    Returns:
        A ConsiderReading with the (possibly inaccurate) prose reading.
    """
    from world.checks.services import (  # noqa: PLC0415
        level_opposition,
        perform_check,
    )
    from world.combat.models import ConsiderReading  # noqa: PLC0415
    from world.progression.services.skill_development import (  # noqa: PLC0415
        get_character_path_level,
    )

    # Return cached reading if it exists — no re-rolls.
    cached = ConsiderReading.objects.filter(participant=participant, opponent=opponent).first()
    if cached is not None:
        return cached

    sheet = participant.character_sheet
    character = sheet.character
    is_enhanced = _has_engaged_assessment_role(sheet)

    check_type = ensure_consider_check_type()
    difficulty = level_opposition(check_type, level=opponent.level, character=opponent.objectdb)
    result = perform_check(
        character,
        check_type,
        target_difficulty=difficulty,
    )
    success_level = result.success_level

    # Compute the player's level for the gap.
    player_level = get_character_path_level(character)
    gap = opponent.level - player_level

    # Determine band set and true index.
    fine = is_enhanced
    bands = FINE_BANDS if fine else COARSE_BANDS
    max_index = len(bands) - 1
    true_index = gap_to_band_index(gap, fine=fine)

    # Apply skew on failure.
    skew = skew_for_success_level(success_level)
    reported_index = apply_skew(true_index, skew, character, max_index=max_index)

    # Assemble prose.
    band_text = band_prose(reported_index, fine=fine)
    tier_text = _tier_prose(opponent)

    # Enhanced extras: only on a precise reading (success_level >= 5).
    extras = ""
    if is_enhanced and success_level >= _SKEW_PRECISE_FLOOR + 4:
        health_text = health_band(opponent.health, opponent.max_health)
        extras = f", {health_text}"

    parts = [f"The {opponent.name} is {band_text}"]
    if tier_text:
        parts.append(f" — {tier_text}")
    if extras:
        parts.append(extras)
    parts.append(".")
    prose = "".join(parts)

    return ConsiderReading.objects.create(
        participant=participant,
        opponent=opponent,
        success_level=success_level,
        true_band_index=true_index,
        reported_band_index=reported_index,
        prose=prose,
        is_enhanced=is_enhanced,
    )
