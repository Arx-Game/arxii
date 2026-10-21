"""Result types for the skills services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillTrainingResult:
    """What :func:`world.skills.services.train_skill` did to one skill.

    ``points_applied`` is the amount that went in after any stop-at-boundary clamp, and
    is what the audit ``DevelopmentTransaction`` records. ``plateau_message`` is set when
    points dissipated at an XP boundary.
    """

    old_value: int
    new_value: int
    points_applied: int
    plateau_message: str | None
