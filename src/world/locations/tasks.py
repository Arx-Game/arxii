"""Periodic task definitions for the locations app."""

from __future__ import annotations

import logging

from world.locations.services import cleanup_decayed_modifiers

logger = logging.getLogger("world.locations.tasks")


def decayed_modifier_cleanup_task() -> None:
    """Delete LocationStatModifier rows whose current_value() has decayed to zero."""
    deleted = cleanup_decayed_modifiers()
    logger.info("Location modifier cleanup: %d decayed modifiers deleted", deleted)
