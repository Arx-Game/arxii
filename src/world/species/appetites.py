"""Appetite anchoring (#2853) — tag-identified, the ADR-0179 pattern.

Two Distinctions are the single mechanical anchor for hunger: ``Appetite:
Blood`` (vampire, dhampir — the bite) and ``Appetite: Essence`` (Vulpi,
Vesperi, shades — touch/magic drain). Species stamp them innately through
``SpeciesGiftGrant.drawback_distinction``; the Shade condition grants one on
application. Everything downstream (regen skip, upkeep, feeding modes)
resolves from held tags, never from species probes.
"""

from __future__ import annotations

from django.db import models

APPETITE_BLOOD_TAG = "appetite-blood"
APPETITE_ESSENCE_TAG = "appetite-essence"
APPETITE_BLOOD_SLUG = "appetite-blood"
APPETITE_ESSENCE_SLUG = "appetite-essence"
APPETITE_TAGS = (APPETITE_BLOOD_TAG, APPETITE_ESSENCE_TAG)
# Shade undeath is its own anchor so the daily drain never touches the
# half-living essence holders (Vulpi/Vesperi carry NO drain — ruled).
SHADE_TAG = "undead-shade"
SHADE_SLUG = "undead-shade"

# --- Ravenous (the hunger tell) — PLACEHOLDER magnitudes ---
RAVENOUS_NAME = "Ravenous"
# Hungry when current anima sits at/below this percent of maximum.
RAVENOUS_THRESHOLD_PERCENT = 25
RAVENOUS_MAX_SEVERITY = 5

# --- Glut (#2853, ruled): decaying overfill; stolen life answers the sun ---
GLUT_DECAY_PER_DAY = 1
# Felt-sun-exposure mitigation per glut point, for sun-sensitive appetite holders.
GLUT_SUN_MITIGATION_FACTOR = 1


class AppetiteKind(models.TextChoices):
    """Which hunger a character carries (worst case: both resolve identically)."""

    NONE = "none", "None"
    BLOOD = "blood", "Blood"
    ESSENCE = "essence", "Essence"


def appetite_for(sheet) -> AppetiteKind:
    """The character's appetite kind by held DistinctionTag; BLOOD wins ties."""
    if sheet is None:
        return AppetiteKind.NONE
    slugs = set(
        sheet.distinctions.filter(
            distinction__tags__slug__in=APPETITE_TAGS,
        ).values_list("distinction__tags__slug", flat=True)
    )
    if APPETITE_BLOOD_TAG in slugs:
        return AppetiteKind.BLOOD
    if APPETITE_ESSENCE_TAG in slugs:
        return AppetiteKind.ESSENCE
    return AppetiteKind.NONE
