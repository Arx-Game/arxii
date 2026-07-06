"""Compatibility facade for ``world.seeds.game_content.combat`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.combat`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.combat``.
"""

from world.seeds.game_content.combat import (
    FleeSeedResult,
    PenetrationContestResult,
    seed_encounter_beat_wiring,
    seed_flee_check,
    seed_penetration_contest,
)

__all__ = [
    "FleeSeedResult",
    "PenetrationContestResult",
    "seed_encounter_beat_wiring",
    "seed_flee_check",
    "seed_penetration_contest",
]
