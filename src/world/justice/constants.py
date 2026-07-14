"""Constants for the justice app — heat tiers, decay, default law posture (#1765).

All magnitudes and the intermediate tier names are PLACEHOLDER pending the
tuning/naming pass.
"""

from django.db import models

# PLACEHOLDER magnitudes (tuning pass pending).
DEFAULT_HEAT_WEIGHT = 10
HEAT_DECAY_PER_DAY = 5

# --- Crime evidence (#1825) — all PLACEHOLDER magnitudes -----------------------------
# Difficulty of the gather/dispose Skulduggery checks (and the untampered examine).
EVIDENCE_BASE_QUALITY = 10
# When ALL of a deed's evidence is DISPOSED, deed-knowledge heat accrual is scaled to
# this percentage (the "much less likely to be discovered" dampener).
DISPOSED_EVIDENCE_HEAT_FACTOR = 25

GATHER_EVIDENCE_CHECK_NAME = "Gather Evidence"
FORGE_EVIDENCE_CHECK_NAME = "Forge Evidence"
SCRUTINIZE_EVIDENCE_CHECK_NAME = "Scrutinize Evidence"


class EvidenceState(models.TextChoices):
    """Lifecycle of one crime's physical evidence (#1825).

    AT_SCENE → GATHERED (a real inventory item) → DISPOSED (destroyed, trail
    dampened) / TAMPERING (a frame-job project is perverting it) → OFF_GRID
    (the frame filed; consumed into the case file) → PRODUCED (an authority
    pulled it back out for examination).
    """

    AT_SCENE = "at_scene", "At the scene"
    GATHERED = "gathered", "Gathered"
    TAMPERING = "tampering", "Being tampered with"
    DISPOSED = "disposed", "Disposed of"
    OFF_GRID = "off_grid", "Off-grid (case file)"
    PRODUCED = "produced", "Produced for examination"


class HeatTier(models.TextChoices):
    """Player-facing pursuit ratings, colour-coded — never a raw number.

    All four hot names are user-ratified (Apostate, 2026-07-02); only the
    thresholds remain PLACEHOLDER.
    """

    SAFE = "safe", "Safe"
    TENSE = "tense", "Tense"
    DANGEROUS = "dangerous", "Dangerous"
    HEAT_IS_ON = "heat_is_on", "The Heat Is On"
    EXTREME_HEAT = "extreme_heat", "Extreme Heat"


# Ascending (tier, minimum value) ladder; PLACEHOLDER thresholds.
HEAT_TIER_FLOORS: tuple[tuple[HeatTier, int], ...] = (
    (HeatTier.EXTREME_HEAT, 100),
    (HeatTier.HEAT_IS_ON, 60),
    (HeatTier.DANGEROUS, 25),
    (HeatTier.TENSE, 1),
    (HeatTier.SAFE, 0),
)


def tier_for_value(value: int) -> HeatTier:
    """Map a summed heat value onto its display tier."""
    for tier, floor in HEAT_TIER_FLOORS:
        if value >= floor:
            return tier
    return HeatTier.SAFE
