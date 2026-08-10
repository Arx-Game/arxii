"""Constants for the predator ecology (#3093) — PLACEHOLDER magnitudes.

The ruling that shapes every number here: menace builds SLOWLY. Roughly ten
weekly crons separate the first rumor from an actual raid, through small,
legible intermediate steps players have ample time to answer.
"""

from django.db import models


class MenaceStage(models.TextChoices):
    """A predator band's escalation ladder (#3093). Advance only when unanswered."""

    RUMORS = "rumors", "Rumors"
    LAWLESSNESS = "lawlessness", "Lawlessness"
    ROBBERY = "robbery", "Robbery"
    RAIDS = "raids", "Raids"
    TERROR = "terror", "Terror"


# Weeks a band must sit UNANSWERED at each stage before advancing to the next.
# Totals ~10 crons from first rumor to terror (Apostate's pacing ruling).
STAGE_WEEKS: dict[str, int] = {
    MenaceStage.RUMORS: 2,
    MenaceStage.LAWLESSNESS: 2,
    MenaceStage.ROBBERY: 4,
    MenaceStage.RAIDS: 2,
}

_STAGE_ORDER: tuple[str, ...] = (
    MenaceStage.RUMORS,
    MenaceStage.LAWLESSNESS,
    MenaceStage.ROBBERY,
    MenaceStage.RAIDS,
    MenaceStage.TERROR,
)

# Weekly unrest added to the prey's domains while lawlessness reigns.
LAWLESSNESS_UNREST_TICK = 1

# Percent of the prey's uncollected income pools skimmed weekly at ROBBERY+.
ROBBERY_SKIM_PCT = 5

# Raid crises open at these severities per stage.
RAID_SEVERITY_BY_STAGE: dict[str, str] = {
    MenaceStage.RAIDS: "crisis",
    MenaceStage.TERROR: "catastrophe",
}

# Counterplay: answering a band (resolved raid, sabotage, hunt) burns strength
# and knocks the ladder down.
STRIKE_STRENGTH_BURN = 25
SABOTAGE_STRENGTH_BURN = 15

# Below this strength a struck band goes dormant instead of merely regressing;
# at zero it disbands outright.
DORMANCY_FLOOR = 20
DORMANCY_WEEKS = 8

# Weekly chance (percent) that a new band spawns menacing a realm with none.
BAND_SPAWN_PCT = 4

# --- Afflictions (#3093): deterrence-blind, slow-burning ---
# Weekly chance (percent) a realm shows Affliction SIGNS (warning tidings only);
# an unconverted sign becomes an open crisis the following week.
AFFLICTION_SIGN_PCT = 3
# Weekly chance an unresolved spreading affliction jumps one domain (same realm).
AFFLICTION_SPREAD_PCT = 25
# Total spreads allowed from one root outbreak.
AFFLICTION_SPREAD_MAX = 3
