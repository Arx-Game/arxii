"""Service functions for the Companion substrate (#672)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone
from evennia.utils.create import create_object

from world.magic.constants import EffectKind, TargetKind
from world.magic.services.pull_effects import get_pull_effects_for_thread

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.companions.models import Companion, CompanionArchetype
    from world.magic.models.gifts import Gift


class NoCompanionThreadError(Exception):
    """Raised when the character has no active GIFT thread for the granting gift."""


def _companion_thread(character_sheet: CharacterSheet, gift: Gift):
    from world.magic.models.threads import Thread  # noqa: PLC0415 — avoid circular import

    thread = Thread.objects.filter(
        owner=character_sheet,
        target_kind=TargetKind.GIFT,
        target_gift=gift,
        retired_at__isnull=True,
    ).first()
    if thread is None:
        msg = f"{character_sheet} has no active thread for gift {gift}."
        raise NoCompanionThreadError(msg)
    return thread


def companion_capacity(character_sheet: CharacterSheet, gift: Gift) -> int:
    """Total Companion Capacity character_sheet has via gift's Thread level.

    Sums tier-0 (passive, always-on) FLAT_BONUS ThreadPullEffect rows whose
    min_thread_level is at or below the thread's current level — mirrors the
    ``row.min_thread_level > thread.level`` skip idiom in world/magic/handlers.py.
    """
    thread = _companion_thread(character_sheet, gift)
    rows = get_pull_effects_for_thread(thread, tier=0, effect_kind=EffectKind.FLAT_BONUS)
    return sum(row.flat_bonus_amount for row in rows if row.min_thread_level <= thread.level)


def used_companion_capacity(character_sheet: CharacterSheet, gift: Gift) -> int:
    """Companion Capacity currently consumed by character_sheet's active companions via gift."""
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    active = Companion.objects.filter(
        owner=character_sheet,
        granting_gift=gift,
        released_at__isnull=True,
    ).select_related("archetype")
    return sum(c.archetype.capacity_cost for c in active)


def bind_companion(
    *,
    owner: CharacterSheet,
    archetype: CompanionArchetype,
    granting_gift: Gift,
    name: str,
) -> Companion:
    """Create a bonded Companion + its live CompanionObject in owner's current room.

    The caller (the Bind Action, Task 8) is responsible for the capacity
    check and the perform_check roll before calling this — this function has
    no prerequisite logic of its own, mirroring the service-function/Action
    split used throughout src/actions/.
    """
    from typeclasses.companions import CompanionObject  # noqa: PLC0415 — avoid circular import
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    room = owner.character.location
    companion_object = create_object(CompanionObject, key=name, location=room, nohome=True)
    return Companion.objects.create(
        owner=owner,
        archetype=archetype,
        granting_gift=granting_gift,
        name=name,
        objectdb=companion_object,
    )


def release_companion(companion: Companion) -> None:
    """Release a bonded companion: destroy its live object, keep the row.

    The Companion row is never hard-deleted — released_at is set and
    objectdb is cleared.
    """
    if companion.objectdb is not None:
        companion.objectdb.delete()
    companion.released_at = timezone.now()
    companion.objectdb = None
    companion.save(update_fields=["released_at", "objectdb"])
