"""Periodic task definitions for worship (#4333 slice 3)."""

from __future__ import annotations

from datetime import timedelta

from world.game_clock.task_registry import CronDefinition, register_task


def register_all_tasks() -> None:
    """Register worship's periodic tasks with the game-clock scheduler.

    Held answers: an answer drawn at a pledge's close while the being's worship
    pool was short is sent as a vision once the pool can pay. Steward answers
    (slice 4): a stewarded being's closing prompt left past its window draws an
    authored answer.
    """
    from world.worship.answer_services import deliver_held_answers  # noqa: PLC0415
    from world.worship.steward_services import expire_steward_prompts  # noqa: PLC0415

    register_task(
        CronDefinition(
            task_key="worship.held_answers",
            callable=deliver_held_answers,
            interval=timedelta(hours=24),
            description="Deliver held pledge answers whose being's worship pool can now pay.",
        )
    )
    register_task(
        CronDefinition(
            task_key="worship.steward_answer_timeout",
            callable=expire_steward_prompts,
            interval=timedelta(hours=1),
            description=(
                "Draw an authored answer for each stewarded being's closing prompt left "
                "unanswered past Devotion config's steward answer days."
            ),
        )
    )
