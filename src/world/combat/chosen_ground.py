"""Chosen-ground stamp helper (#2646).

``compute_on_chosen_ground`` decides whether a combat encounter about to be
created is fighting on ground the caster's side prepared ahead of time — "the
fight was won yesterday." Called from the three PC-vs-NPC encounter-creation
seams (``world.combat.cast_seed.seed_or_feed_encounter_from_cast``,
``world.combat.duels.create_lethal_duel``, ``world.battles.services.
open_place_encounter``) to stamp ``CombatEncounter.on_chosen_ground`` at
creation time. ``world.combat.duels.create_pvp_duel`` deliberately never calls
this (PvP is never lethal, so "chosen ground" does not apply).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.room_features.models import PreparedGround

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def compute_on_chosen_ground(room: ObjectDB | None) -> bool:  # noqa: OBJECTDB_PARAM
    """True iff *room* holds a ``PreparedGround`` whose preparer is physically present.

    ``room`` is the ObjectDB room a new ``CombatEncounter`` is about to be created
    in (or ``None``, e.g. a roomless duel path — reads as False). A room with no
    ``RoomProfile`` (no game-world extension row) trivially has no prepared ground.
    Iterates every ``PreparedGround`` row on the room's profile (a room may have
    at most one active prepared ground per character, never more than a handful at
    once) and returns True as soon as one preparer's character is actually
    standing in *room* right now — a ground prepared but then abandoned does not
    count.
    """
    if room is None:
        return False
    try:
        profile = room.room_profile
    except ObjectDoesNotExist:
        return False
    grounds = PreparedGround.objects.filter(room_profile=profile).select_related("prepared_by")
    for ground in grounds:
        character = ground.prepared_by.character
        if character is not None and character.location == room:
            return True
    return False
