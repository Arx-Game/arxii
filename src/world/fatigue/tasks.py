"""Periodic tasks for the fatigue system."""

from __future__ import annotations

import logging

from world.fatigue.models import FatiguePool
from world.fatigue.services import reset_fatigue
from world.roster.selectors import get_account_for_character
from world.scenes.models import SceneParticipation

logger = logging.getLogger("world.fatigue.tasks")


def fatigue_dawn_reset_task() -> None:
    """Reset fatigue for all characters at IC dawn.

    Characters currently in active scenes get dawn_deferred=True instead
    of an immediate reset. Deferred resets are processed when the scene
    finishes via process_deferred_fatigue_resets().
    """
    # Pre-compute the set of account IDs currently in active scenes
    accounts_in_scenes: set[int] = set(
        SceneParticipation.objects.filter(
            scene__is_active=True,
            left_at__isnull=True,
        ).values_list("account_id", flat=True)
    )

    pools = list(FatiguePool.objects.select_related("character__character").all())
    reset_count = 0
    deferred_count = 0

    for pool in pools:
        character_obj = pool.character.character  # CharacterSheet -> ObjectDB
        account = get_account_for_character(character_obj)

        if account is not None and account.pk in accounts_in_scenes:
            pool.dawn_deferred = True
            pool.save(update_fields=["dawn_deferred"])
            deferred_count += 1
        else:
            reset_fatigue(pool.character)
            reset_count += 1

    logger.info("Dawn fatigue reset: %d reset, %d deferred", reset_count, deferred_count)


def process_deferred_fatigue_resets(scene_account_ids: set[int]) -> int:
    """Reset fatigue for participants whose dawn reset was deferred.

    Called after a scene finishes. Checks each deferred pool to see if
    its character's account was a participant in the finished scene.

    Args:
        scene_account_ids: Set of account PKs that participated in the
            finished scene.

    Returns:
        Number of deferred resets processed.
    """
    deferred_pools = list(
        FatiguePool.objects.filter(dawn_deferred=True).select_related("character__character")
    )
    count = 0

    for pool in deferred_pools:
        character_obj = pool.character.character
        account = get_account_for_character(character_obj)

        if account is not None and account.pk in scene_account_ids:
            reset_fatigue(pool.character)
            count += 1

    if count:
        logger.info("Deferred fatigue reset: %d pools reset after scene end", count)

    return count
