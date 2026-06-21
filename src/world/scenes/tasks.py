"""Periodic task definitions for the scenes app."""

from __future__ import annotations

import logging

from django.utils import timezone

from world.scenes.block_services import finalize_expired_blocks

logger = logging.getLogger("world.scenes.tasks")


def block_finalize_task() -> None:
    """Finalize blocks whose lift grace period has elapsed (#1278).

    A lifted block stays active until ``pending_removal_at`` (set to a future cron tick), so a
    player can't lift → snipe → re-block. This sweep removes the ones whose grace window has now
    passed.
    """
    removed = finalize_expired_blocks(now=timezone.now())
    logger.info("Block finalize: %d lifted blocks removed", removed)
