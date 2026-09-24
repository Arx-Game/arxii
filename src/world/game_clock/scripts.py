"""Evennia Script for the game clock scheduler."""

from __future__ import annotations

import logging

from django.db import close_old_connections
import evennia

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
        # Discard dead/expired DB connections BEFORE any query. The Server is
        # a long-lived process holding one main-thread Django connection; a
        # Postgres restart under it (e.g. unattended-upgrades) leaves that
        # connection dead, and every Twisted-side query then raises
        # OperationalError("the connection is closed") until something closes
        # it — including Evennia's own shutdown(), whose FIRST statement is a
        # ServerConfig query, which is how `evennia reload` wedged forever on
        # 2026-08-23 (four deploys stranded). Web requests self-heal via
        # Django's request_started signal; this is the equivalent for the
        # tick path. close() is local (no server roundtrip), so this never
        # raises, and the next query transparently reopens — bounding the
        # dead-connection window to one TICK_INTERVAL.
        close_old_connections()
        rearm_maintenance_loop()
        ic_now = get_ic_now()
        executed = run_due_tasks(ic_now=ic_now)
        if executed:
            logger.info("Tick completed, ran tasks: %s", ", ".join(executed))


def rearm_maintenance_loop() -> None:
    """Restart Evennia's once-a-minute maintenance loop if it has died (#4001).

    A twisted LoopingCall stops for good when its function raises, and
    ``server_maintenance`` raises the moment its runtime save meets a dead
    connection (a Postgres restart under the Server). That loop is what saves
    runtime, processes idle timeouts, flushes the idmapper and drops the
    connection every seven hours; nothing else ever restarts it. Runs after
    ``close_old_connections`` so the first call the revived loop makes
    reconnects instead of failing again.
    """
    service = evennia.EVENNIA_SERVER_SERVICE
    if service is None:
        # Outside a running Server (tests, shell) there is no loop to keep.
        return
    task = service.maintenance_task
    if task is None or task.running:
        return
    logger.warning("Evennia maintenance loop was stopped; re-arming it.")
    task.start(60, now=False)


def ensure_game_tick_script() -> None:
    """Create the GameTickScript if it doesn't already exist, and make sure it ticks.

    A row is not a timer. Evennia re-arms a persistent script at boot only
    through ``_unpause_task(auto_unpause=True)``, which needs the
    ``_paused_time`` a graceful stop stores; a hard kill stores nothing, so the
    row stays ``db_is_active=True`` with no timer across every later boot.
    Production ran that way from the 2026-08-23 SIGKILL recovery until #3993,
    with the tick-level connection heal (#3327) deployed and never ticking.
    """
    from evennia.utils.create import create_script

    script = GameTickScript.objects.first()
    if script:
        # None means no live timer: Evennia's public view of ``ndb._task``.
        if script.time_until_next_repeat() is not None:
            logger.info("GameTickScript already exists and is ticking.")
            return
        script.start()
        logger.warning("GameTickScript existed without a running timer; re-armed it.")
        return

    script = create_script(
        GameTickScript,
        key=SCRIPT_KEY,
        persistent=True,
        interval=TICK_INTERVAL,
    )
    logger.info("Created GameTickScript: %s", script)
