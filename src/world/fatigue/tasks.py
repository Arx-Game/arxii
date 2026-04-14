"""Periodic tasks for the fatigue system."""

from __future__ import annotations

import logging

from world.fatigue.models import FatiguePool
from world.fatigue.services import reset_fatigue
from world.roster.models import RosterTenure
from world.scenes.models import SceneParticipation

logger = logging.getLogger("world.fatigue.tasks")


def _build_character_to_account_map(character_pks: list[int]) -> dict[int, int]:
    """Build a mapping from character ObjectDB PK to account PK.

    Uses a single RosterTenure query instead of per-character lookups.

    Args:
        character_pks: List of ObjectDB primary keys.

    Returns:
        Dict mapping character PK to account PK for characters with active tenures.
    """
    tenures = (
        RosterTenure.objects.filter(
            roster_entry__character_sheet_id__in=character_pks,
            end_date__isnull=True,
        )
        .select_related("player_data")
        .values_list("roster_entry__character_sheet_id", "player_data__account_id")
    )
    return dict(tenures)


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

    pools = list(FatiguePool.objects.select_related("character_sheet__character").all())

    # Batch lookup: character ObjectDB PK -> account PK
    character_pks = [pool.character_sheet.character_id for pool in pools]
    char_to_account = _build_character_to_account_map(character_pks)

    reset_count = 0
    deferred_count = 0

    for pool in pools:
        character_obj = pool.character_sheet.character  # CharacterSheet -> ObjectDB
        account_pk = char_to_account.get(character_obj.pk)

        if account_pk is not None and account_pk in accounts_in_scenes:
            pool.dawn_deferred = True
            pool.save(update_fields=["dawn_deferred"])
            deferred_count += 1
        else:
            reset_fatigue(pool.character_sheet)
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
        FatiguePool.objects.filter(dawn_deferred=True).select_related("character_sheet__character")
    )

    # Batch lookup: character ObjectDB PK -> account PK
    character_pks = [pool.character_sheet.character_id for pool in deferred_pools]
    char_to_account = _build_character_to_account_map(character_pks)

    count = 0

    for pool in deferred_pools:
        character_obj = pool.character_sheet.character
        account_pk = char_to_account.get(character_obj.pk)

        if account_pk is not None and account_pk in scene_account_ids:
            reset_fatigue(pool.character_sheet)
            count += 1

    if count:
        logger.info("Deferred fatigue reset: %d pools reset after scene end", count)

    return count
