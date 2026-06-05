"""Periodic tasks for the societies + renown system (#676 Phase A).

Registered with ``world.game_clock.task_registry`` at server startup.
Renown decay runs per IC day; with the canonical 3:1 IC:OOC time ratio,
that's every 8 real hours.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from world.game_clock.task_registry import CronDefinition, register_task
from world.societies.renown import decay_all_org_accumulated, decay_all_persona_fame

logger = logging.getLogger(__name__)


# Interval picked to match one IC day under the canonical 3:1 IC:OOC ratio
# (GameClock.time_ratio default = 3.0). If the ratio is ever retuned, this
# constant needs revisiting in lockstep with the spec's tier-duration math
# (see issue #676 Renown spec).
RENOWN_DECAY_INTERVAL = timedelta(hours=8)


def renown_fame_decay_task() -> None:
    """Cron entry: decay fame on every persona with positive buffer."""
    decay_all_persona_fame()


def renown_org_decay_task() -> None:
    """Cron entry: decay accumulated_prestige + accumulated_fame on orgs."""
    decay_all_org_accumulated()


def register_all_tasks() -> None:
    """Register the renown decay tasks with the game-clock scheduler."""
    register_task(
        CronDefinition(
            task_key="renown.fame_decay",
            callable=renown_fame_decay_task,
            interval=RENOWN_DECAY_INTERVAL,
            description=(
                "Apply per-IC-day fame decay to every persona with positive "
                "fame_points (Renown system #676)."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="renown.org_accumulated_decay",
            callable=renown_org_decay_task,
            interval=RENOWN_DECAY_INTERVAL,
            description=(
                "Apply per-IC-day decay to org accumulated_prestige + "
                "accumulated_fame (Renown system #676). Permanent fields "
                "(base_prestige, accumulated_legend on covenants) are not "
                "touched."
            ),
        )
    )
