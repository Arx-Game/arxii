"""Service helpers for the classes app."""

from world.classes.models import PathStage

# (min_level, stage) descending — first whose min_level <= level wins.
_STAGE_THRESHOLDS: list[tuple[int, int]] = [
    (21, PathStage.TRANSCENDENT),
    (16, PathStage.GRAND),
    (11, PathStage.TRUE),
    (6, PathStage.PUISSANT),
    (3, PathStage.POTENTIAL),
    (1, PathStage.PROSPECT),
]


def stage_for_level(level: int) -> int:
    """Map a class level to its PathStage value (clamps <1 to PROSPECT)."""
    for min_level, stage in _STAGE_THRESHOLDS:
        if level >= min_level:
            return stage
    return PathStage.PROSPECT
