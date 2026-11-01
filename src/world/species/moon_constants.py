"""Tuning constants for the moon pull and lycan control checks (#2845).

The pull's own magnitudes. The control check's tuning (difficulty, relief, exemption,
consequences) is authored on the moon's ControlLossTrigger row (#4802). The shapes are the
design, the numbers first-cut values arranged to satisfy the #2845 tuning invariants (see
world/species/tests/test_moon_pull.py and the spec on the issue):

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

# --- Battle-form clarity scaling ---
# instance_value multiplier at shift time: 1.0 baseline (day/indoors), rising
# with felt moonlight to 1.0 + MOON_FORM_CLARITY_MAX_BONUS under a clear full
# moon. Applies to voluntary shifts too — the moon empowers the form
# regardless of who chose the shift.
MOON_FORM_CLARITY_MAX_BONUS = 0.5

# --- Cani unease (ruled 2026-07-31: the Cani umbrella carries it) ---
CANI_SPECIES_NAME = "Cani"
MOONLIT_UNEASE_NAME = "Moonlit Unease"
