"""Shared builders for stubbing ``start_action_resolution`` in action/command tests.

``start_action_resolution`` returns a ``PendingActionResolution``; these helpers build
that real production type (with a real ``StepResult`` + ``CheckResult``) so tests exercise
the load-bearing ``main_result.check_result.success_level`` read instead of a stand-in
``ActionResult`` that only happens to expose ``.success`` (#1245).

Kept separate from the scene-specific ``world.scenes.tests.cast_test_helpers`` — that one
returns the cast-only ``EnhancedSceneActionResult`` wrapper, hardcodes success, and lives
in the scenes layer; these return the raw resolution and take a success level.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from actions.types import PendingActionResolution, StepResult
from world.checks.types import CheckResult


def make_resolution(success_level: int) -> PendingActionResolution:
    """A completed ``PendingActionResolution`` whose main step rolled ``success_level``."""
    check_result = CheckResult(
        check_type=MagicMock(),
        outcome=MagicMock(success_level=success_level),
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    step = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=0,
        character_id=0,
        target_difficulty=0,
        resolution_context_data={},
        current_phase="main",
        main_result=step,
    )


def make_paused_resolution() -> PendingActionResolution:
    """A paused ``PendingActionResolution`` whose main step has not rolled yet."""
    return PendingActionResolution(
        template_id=0,
        character_id=0,
        target_difficulty=0,
        resolution_context_data={},
        current_phase="gate",
        main_result=None,
    )
