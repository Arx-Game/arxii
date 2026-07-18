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


# --- Heat lifecycle (#1826) — PLACEHOLDER magnitudes ---
# Lying low: declared state; extra decay in the declared area while active,
# and the persona's rackets miss them (CRIME_KICKUP gross malus at collection).
LIE_LOW_DECAY_MULT = 3
LIE_LOW_CRIME_MALUS_PCT = 25

# Heat value at/above which a persona's warrant becomes publicly visible
# (wanted posters). Maps to the top two tiers of HEAT_TIER_FLOORS.
WANTED_VALUE_FLOOR = 60

# Bribing the hunters: coin cost per point of current heat; cleared fraction
# by check band; the botch band mints a bribery crime of its own.
BRIBE_COST_PER_HEAT = 50
BRIBE_CLEAR_PCT = 60
BRIBE_PARTIAL_CLEAR_PCT = 30
BRIBE_BOTCH_LEVEL = -2
BRIBE_CHECK_TYPE_NAME = "Bribery Approach"
BRIBERY_CRIME_SLUG = "bribery"
BRIBERY_CRIME_SCALE = 2

# OrganizationOffice slug whose holder (in an org of the enforcing society)
# may pardon — the delegation payoff, mirroring domain-steward (#2239).
MAGISTRATE_OFFICE = "magistrate"


# --- Justice pipeline (#2378) — PLACEHOLDER magnitudes ---
# Trigger ladder floors (reuse the tier ladder): below HUNTED, only direct NPC
# transactions can trigger; at HUNTED any public NPC interaction; at MAX every
# public room arrival rolls.
HUNTED_VALUE_FLOOR = 100
MAX_VALUE_FLOOR = 150

# Encounter chance (percent) per trigger kind, rolled only during active play.
GUARD_ENCOUNTER_PCT_NPC_TRANSACTION = 25
GUARD_ENCOUNTER_PCT_PUBLIC_INTERACTION = 15
GUARD_ENCOUNTER_PCT_ROOM_ARRIVAL = 10

EVASION_CHECK_TYPE_NAME = "Guard Evasion"
EVASION_BOTCH_LEVEL = -2
EVASION_ESCAPE_HEAT_BUMP = 5

ADVOCACY_CHECK_TYPE_NAME = "Court Advocacy"
ADVOCACY_WEIGHT_PER_LEVEL = 5

# Exculpatory evidence: real submissions carry fixed weight; manufactured ones
# are check-banded. Release threshold scales with the case's prosecution weight.
EVIDENCE_WEIGHT_REAL = 10
EVIDENCE_WEIGHT_MANUFACTURED_MAX = 8
RELEASE_THRESHOLD_FACTOR = 2  # threshold = prosecution_weight // FACTOR, min 10
EVIDENCE_TAMPERING_CRIME_SLUG = "evidence-tampering"
EVIDENCE_TAMPERING_SCALE = 2

# Sentencing (verdict = defense-prosecution margin).
VERDICT_ACQUIT_MARGIN = 0
VERDICT_LESSER_MARGIN = -10
FINE_COPPERS_PER_WEIGHT = 100
BRIG_DAYS_PER_WEIGHT = 1
# The lethal wall (ADR-0023): PC execution needs the target's OOC opt-in AND a
# spectacularly-exhausted case — never a single roll.
EXECUTION_MIN_FAILED_OUTS = 2


class GuardTrigger(models.TextChoices):
    NPC_TRANSACTION = "npc_transaction", "NPC Transaction"
    PUBLIC_INTERACTION = "public_interaction", "Public Interaction"
    ROOM_ARRIVAL = "room_arrival", "Room Arrival"


class EncounterOutcome(models.TextChoices):
    ESCAPED = "escaped", "Escaped Clean"
    ESCAPED_SEEN = "escaped_seen", "Escaped, Seen"
    CAPTURED = "captured", "Captured"


class CaseStatus(models.TextChoices):
    AWAITING_TRIAL = "awaiting_trial", "Awaiting Trial"
    RELEASED_EVIDENCE = "released_evidence", "Released (Evidence)"
    RELEASED_PARDON = "released_pardon", "Released (Pardon)"
    TRIED = "tried", "Tried"


class Verdict(models.TextChoices):
    ACQUITTED = "acquitted", "Acquitted"
    LESSER = "lesser", "Guilty (Lesser)"
    FULL = "full", "Guilty"


class SentenceKind(models.TextChoices):
    FINE = "fine", "Fine"
    BRIG_TERM = "brig_term", "Imprisonment"
    HUMILIATION = "humiliation", "Public Humiliation"
    EXILE = "exile", "Exile"
    EXECUTION = "execution", "Execution"
