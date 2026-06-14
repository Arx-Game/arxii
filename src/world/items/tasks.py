"""Periodic tasks for the fashion / trendsetter system (Outfits Phase C, #514).

Registered with ``world.game_clock.task_registry`` at server startup via the
aggregator in ``world.game_clock.tasks.register_all_tasks``.
"""

from __future__ import annotations

import logging

from world.game_clock.task_registry import CronDefinition, register_task
from world.items.constants import FASHION_SEASON_INTERVAL, FASHION_VOGUE_DECAY_INTERVAL
from world.items.services.trendsetter import (
    run_all_trendsetter_ceremonies,
    vogue_momentum_decay_tick,
)

logger = logging.getLogger(__name__)


def trendsetter_ceremony_task() -> None:
    """Cron entry: run the seasonal trendsetter ceremony for every society."""
    crowned = run_all_trendsetter_ceremonies()
    logger.info("Trendsetter ceremony: crowned %d trendsetter(s)", len(crowned))


def vogue_momentum_decay_task() -> None:
    """Cron entry: decay all positive facet-vogue momentum toward zero."""
    vogue_momentum_decay_tick()


def register_all_tasks() -> None:
    """Register the fashion periodic tasks with the game-clock scheduler."""
    register_task(
        CronDefinition(
            task_key="fashion.trendsetter_ceremony",
            callable=trendsetter_ceremony_task,
            interval=FASHION_SEASON_INTERVAL,
            description=(
                "Seasonal trendsetter ceremony: crown each society's top-acclaim "
                "presenter and rewrite its in-vogue facets from accumulated "
                "vogue momentum (Outfits Phase C, #514)."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="fashion.vogue_momentum_decay",
            callable=vogue_momentum_decay_task,
            interval=FASHION_VOGUE_DECAY_INTERVAL,
            description=(
                "Decay every positive FacetVogueMomentum toward zero, mirroring "
                "the renown fame-decay cadence (Outfits Phase C, #514)."
            ),
        )
    )
