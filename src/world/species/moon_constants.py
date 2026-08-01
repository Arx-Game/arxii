"""Tuning constants for the moon pull and lycan control checks (#2845).

Every magnitude here is a PLACEHOLDER author pass — the shapes are the design,
the numbers are first-cut values arranged to satisfy the #2845 tuning
invariants (see world/species/tests/test_moon_pull.py and the spec on the
issue):

- Only a bright moon under an open night sky pulls at all; clouds dampen it.
- A fresh lycan under a clear full moon faces a genuinely hard control check.
- A mid-tier lycan (level 3) finds the same moon manageable.
- At level 6+ the check never fires unless the character is impaired
  (condition-driven willpower a full tier down — drink, drugs, despair).
- A shift under a clear full moon is more fearsome than a daytime shift.
"""

# --- Base moonlight ---
# Full-moon base at NIGHT under an open sky; scaled by illumination (0..1).
BASE_MOON_FULL = 10

# --- Pull → check gate ---
# The control check fires only when the felt pull reaches this. A half moon
# (base 5) never triggers; a clear full moon (10) always does; cloud shelter
# can drag a full moon below the line.
MOON_PULL_CHECK_THRESHOLD = 6

# --- Control check difficulty ---
# difficulty = BASE + pull × PER_PULL − level × RELIEF_PER_LEVEL − thread relief
MOON_CONTROL_BASE_DIFFICULTY = 20
MOON_CONTROL_DIFFICULTY_PER_PULL = 5
MOON_CONTROL_RELIEF_PER_LEVEL = 10
# Gift-thread mastery: relief per level of the character's thread on the
# species gift, capped so authored content stays the ceiling.
MOON_THREAD_RELIEF_PER_LEVEL = 5
MOON_THREAD_RELIEF_CAP = 30

# --- Tier exemption (ruled 2026-07-31) ---
# At/above this character level the check fires only while impaired:
# condition-driven willpower shifted a full tier (or more) below base.
MOON_EXEMPT_LEVEL = 6
MOON_IMPAIRMENT_WILLPOWER_DROP = 10

# --- Failure consequences ---
MOON_BERSERK_SEVERITY = 3
MOON_BERSERK_DURATION_ROUNDS = 3

# --- Battle-form clarity scaling ---
# instance_value multiplier at shift time: 1.0 baseline (day/indoors), rising
# with felt moonlight to 1.0 + MOON_FORM_CLARITY_MAX_BONUS under a clear full
# moon. Applies to voluntary shifts too — the moon empowers the form
# regardless of who chose the shift.
MOON_FORM_CLARITY_MAX_BONUS = 0.5

# --- Distinction anchoring (#2752 tag pattern; mirrors sun/appetites) ---
MOON_BOUND_TAG = "moon-bound"
MOON_BOUND_SLUG = "moon-bound"

# --- Species gift (named by ApostateCD 2026-07-31; TehomCD may rename) ---
WOLFS_FURY_GIFT_NAME = "The Wolf's Fury"

# --- Cani unease (ruled 2026-07-31: the Cani umbrella carries it) ---
CANI_SPECIES_NAME = "Cani"
MOONLIT_UNEASE_NAME = "Moonlit Unease"

# --- Check content (config rows named by code, ADR-0171) ---
MOON_CONTROL_CHECK_NAME = "moon_control"
MOON_CONTROL_WILLPOWER_WEIGHT = "1.00"
MOON_CONTROL_COMPOSURE_WEIGHT = "0.50"
