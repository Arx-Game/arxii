"""Evennia Script for the game clock scheduler."""

from __future__ import annotations

import logging

from typeclasses.scripts import Script
from world.game_clock.services import get_ic_now
from world.game_clock.task_registry import run_due_tasks

logger = logging.getLogger("world.game_clock.scheduler")

# Tick interval in seconds (5 minutes)
TICK_INTERVAL = 300

# Canonical key for the singleton GameTickScript
SCRIPT_KEY = "game_tick_script"


class GameTickScript(Script):
    """Persistent background script that dispatches periodic tasks."""

    def at_script_creation(self) -> None:
        self.key = SCRIPT_KEY
        self.desc = "Game clock periodic task dispatcher"
        self.interval = TICK_INTERVAL
        self.persistent = True
        self.start_delay = True

    def at_repeat(self) -> None:
        ic_now = get_ic_now()
        executed = run_due_tasks(ic_now=ic_now)
        if executed:
            logger.info("Tick completed, ran tasks: %s", ", ".join(executed))


def ensure_game_tick_script() -> None:
    """Create the GameTickScript if it doesn't already exist."""
    from evennia.utils.create import create_script

    if GameTickScript.objects.first():
        logger.info("GameTickScript already exists, skipping creation.")
        return

    script = create_script(
        GameTickScript,
        key=SCRIPT_KEY,
        persistent=True,
        interval=TICK_INTERVAL,
    )
    logger.info("Created GameTickScript: %s", script)
