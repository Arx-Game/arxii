"""What a character perceives of Primum (#5125).

A caster always knows the substance she works herself, and knows another substance in a place
only once she has sensed it there (a ``PrimumSighting``). The read is what the cast card uses
to decide whether it may name a substance that works against her. A ``REVEAL_PRIMUM`` effect
(a Magesight check) writes the sightings: ``reveal`` names the strongest substance in the place,
or all of them, and ``clear_sightings`` takes them back when she leaves.
"""

from __future__ import annotations

from collections import defaultdict
import contextlib
from typing import TYPE_CHECKING

from django.db.models import Q

from evennia_extensions.models import RoomProfile
from world.character_sheets.models import CharacterSheet
from world.checks.constants import PrimumRevealScope
from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent
from world.magic.models import CharacterGift, CreaturePrimum, PrimumSighting, Substance
from world.magic.services.primum import gift_substance, room_substance_amounts

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def perceived_substance_ids(character: ObjectDB, room: ObjectDB | None) -> frozenset[int]:
    """The substances ``character`` perceives in ``room``.

    The caster's sightings for that room, plus the substance of each gift she holds (resolved
    through the gift's lineage). A character with no sheet perceives nothing.
    """
    try:
        sheet = character.sheet_data
    except CharacterSheet.DoesNotExist:
        return frozenset()
    perceived: set[int] = set()
    for held in CharacterGift.objects.filter(character=sheet).select_related("gift"):
        substance = gift_substance(held.gift)
        if substance is not None:
            perceived.add(substance.pk)
    if room is not None:
        try:
            profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return frozenset(perceived)
        perceived.update(
            PrimumSighting.objects.filter(character_sheet=sheet, room_profile=profile).values_list(
                "substance_id", flat=True
            )
        )
    return frozenset(perceived)


def creature_substance_amounts(room: ObjectDB) -> dict[int, int]:
    """Substance pk to the Primum the creatures in ``room`` carry.

    Counts each opponent of a fight in this room that is still standing, or was slain and has
    not been harvested, at the Primum its kind of creature carries. Creatures add up.
    """
    standing = (
        CombatOpponent.objects.filter(encounter__room=room, creature_template__isnull=False)
        .filter(
            Q(status=OpponentStatus.ACTIVE)
            | Q(status=OpponentStatus.DEFEATED, primum_harvested_at__isnull=True)
        )
        .values_list("creature_template_id", flat=True)
    )
    head_count: dict[int, int] = defaultdict(int)
    for template_id in standing:
        head_count[template_id] += 1
    if not head_count:
        return {}
    amounts: dict[int, int] = defaultdict(int)
    for row in CreaturePrimum.objects.filter(creature_template_id__in=head_count):
        amounts[row.substance_id] += row.amount * head_count[row.creature_template_id]
    return {pk: amount for pk, amount in amounts.items() if amount > 0}


def candidate_substances(room: ObjectDB) -> dict[int, int]:
    """Substance pk to the Primum a Magesight check could name in ``room``.

    The place's amounts and the creatures' amounts, the larger of the two for each substance.
    """
    amounts = room_substance_amounts(room)
    for pk, amount in creature_substance_amounts(room).items():
        amounts[pk] = max(amounts.get(pk, 0), amount)
    return amounts


def reveal(sheet: CharacterSheet, room: ObjectDB, scope: str) -> list[Substance]:
    """Let ``sheet`` perceive the Primum in ``room``; returns the substances now named.

    ``STRONGEST`` names the one with the most Primum (ties go to the first name in order);
    ``ALL`` names every one. A substance she already senses here stays named once.
    """
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return []
    amounts = candidate_substances(room)
    if not amounts:
        return []
    named = list(Substance.objects.filter(pk__in=amounts).order_by("name"))
    if scope == PrimumRevealScope.STRONGEST:
        named = [max(named, key=lambda substance: amounts[substance.pk])]
    known = set(
        PrimumSighting.objects.filter(character_sheet=sheet, room_profile=profile).values_list(
            "substance_id", flat=True
        )
    )
    PrimumSighting.objects.bulk_create(
        [
            PrimumSighting(character_sheet=sheet, room_profile=profile, substance=substance)
            for substance in named
            if substance.pk not in known
        ],
        ignore_conflicts=True,
    )
    return named


def clear_sightings(sheet: CharacterSheet, *, keep_room: ObjectDB | None = None) -> int:
    """Forget what ``sheet`` sensed, everywhere but ``keep_room`` (she left, or went offline)."""
    rows = PrimumSighting.objects.filter(character_sheet=sheet)
    if keep_room is not None:
        with contextlib.suppress(RoomProfile.DoesNotExist):
            rows = rows.exclude(room_profile=keep_room.room_profile)
    deleted, _ = rows.delete()
    return deleted
