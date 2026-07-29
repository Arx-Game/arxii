"""Tuning constants for felt sun exposure and sun sensitivity (#2846).

Every magnitude here is a PLACEHOLDER author pass — the shapes are the design,
the numbers are first-cut values arranged to satisfy the #2846 tuning
invariants (see world/species/tests/test_felt_sun_exposure.py and the spec on
the issue):

- A fully covered vampire is debuffed but takes no damage.
- Parasol + shade keeps a vampire at zero damage in a public outdoor scene.
- Only real shadow (shade/indoors, not clothing) clears a vampire's condition.
- A covered dhampir/nox'alfar feels a token penalty at most.
- A nude allergy-tier sunbather escalates into genuine peril.
"""

from world.items.constants import BodyRegion

# --- Base sunlight by IC phase (only the sun ever feeds this — no other light) ---
BASE_SUN_DAY = 10
BASE_SUN_DAWN_DUSK = 5

# --- Clothing coverage ---
# Body regions where covered skin blocks sun. Fingers/ears are jewelry slots, not coverage.
SUN_COVERAGE_REGIONS: frozenset[str] = frozenset(
    {
        BodyRegion.HEAD,
        BodyRegion.FACE,
        BodyRegion.NECK,
        BodyRegion.SHOULDERS,
        BodyRegion.TORSO,
        BodyRegion.BACK,
        BodyRegion.LEFT_ARM,
        BodyRegion.RIGHT_ARM,
        BodyRegion.LEFT_HAND,
        BodyRegion.RIGHT_HAND,
        BodyRegion.LEFT_LEG,
        BodyRegion.RIGHT_LEG,
        BodyRegion.FEET,
    }
)
SUN_PROTECTION_PER_REGION = 1
# An ordinary full non-revealing outfit maxes out here; hoods/veils/parasols go further
# via authored GarmentMitigation SUN rows, not via more coverage.
CLOTHING_COVERAGE_CAP = 6

# --- Magic ---
# ModifierTarget name spells/conditions/wards write CharacterModifiers against.
# Content-repo-owned (#2698): looked up, never invented outside SEED_SAMPLE_CONTENT.
SUN_MITIGATION_TARGET_NAME = "sun_mitigation"

# --- Sensitivity tiers → condition severity ---
# Bane rides a floor: while meaningful sun reaches the character at all
# (shade-only residual above SHADOW_CLEAR_THRESHOLD), a bane-tier character is
# never below BANE_MINIMUM_SEVERITY — clothing and magic can stop the damage,
# but only real shadow clears the debuff entirely.
BANE_SEVERITY_SHIFT = 1
BANE_MINIMUM_SEVERITY = 1
SHADOW_CLEAR_THRESHOLD = 2
# Allergy tier shrugs off this much residual exposure before feeling anything.
ALLERGY_GRACE = 3

# --- Condition stage thresholds (ConditionStage.severity_threshold values) ---
# Below BURNING: impairment only (check penalties). At/above: radiant DoT.
BURNING_SEVERITY_THRESHOLD = 6
SEARING_SEVERITY_THRESHOLD = 10

# --- Escalation under sustained exposure ---
# Every ESCALATION_IC_HOURS of continuous exposure adds +1 target severity, capped.
ESCALATION_IC_HOURS = 2
ESCALATION_CAP = 4

# --- Hazard response ---
# A successful tough-it-out suppresses re-prompting and auto-flee for this long (IC).
ENDURE_IC_HOURS = 4
# Auto-flee fires after this many observed damage instances with no player response.
AUTO_FLEE_AFTER_DAMAGE_OBSERVATIONS = 2
# Bounded search depth for the nearest sun refuge.
SUN_REFUGE_MAX_DEPTH = 6

# --- Distinction anchoring (#2752 tag pattern) ---
SUN_BANE_TAG = "sun-bane"
SUN_ALLERGY_TAG = "sun-allergy"
SUN_BANE_SLUG = "bane-sunlight"
SUN_ALLERGY_SLUG = "allergy-sunlight"
# Negative cost_per_rank = CG reimbursement (counterweight). PLACEHOLDER magnitudes.
SUN_BANE_CG_COST = -20
SUN_ALLERGY_CG_COST = -8
