"""Stakes-contract engine: readiness validation, activation, effective risk.

#1770 PR1. The contract's data model lives in world.stories.models; this
module owns the rules: is the contract complete (readiness), what does it
actually pay for THIS party (effective risk), and the lock lifecycle
(activation -> resolution).
"""

import logging

from world.societies.constants import RenownRisk
from world.stories.constants import RISK_LADDER

logger = logging.getLogger(__name__)

# Every this-many levels of over-level drops effective risk one tier;
# the same gap under-level raises it, capped at UNDER_LEVEL_MAX_UPGRADE.
# Starting curve per the #1770 spec — designer-tunable by code change only
# deliberately (the ladder shift is an invariant, not content).
LEVELS_PER_TIER = 2
UNDER_LEVEL_MAX_UPGRADE = 1


def risk_index(risk: str) -> int:
    """Position of a RenownRisk value on the weakest->strongest ladder."""
    return RISK_LADDER.index(risk)


def compute_effective_risk(declared_risk: str, target_level: int, party_average_level: int) -> str:
    """What the declared risk is actually worth to this party (#1770 pillar 4).

    'Highly risky to level 4 is not risky at all to level 10 — no chance
    they'd lose, so no stakes.' Over-leveled parties decay toward NONE;
    under-leveled parties get a bounded upgrade. NONE is a fixed point.
    """
    if declared_risk == RenownRisk.NONE:
        return RenownRisk.NONE
    gap = party_average_level - target_level
    if gap >= 0:
        shift = -(gap // LEVELS_PER_TIER)
    else:
        shift = min(UNDER_LEVEL_MAX_UPGRADE, (-gap) // LEVELS_PER_TIER)
    idx = risk_index(declared_risk) + shift
    idx = max(0, min(len(RISK_LADDER) - 1, idx))
    return RISK_LADDER[idx]
