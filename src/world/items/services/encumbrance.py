"""Encumbrance (#2862): generous strength capacity, honest costs above it.

The ruled shape (convenience over believability, clarity over simulation):

- **Under capacity costs nothing, ever.** Nobody gets stuck in a room
  wondering why — movement below the line is always free and silent.
- **Above capacity** each room moved charges physical fatigue (the existing
  pool; the collapse ladder provides the teeth for free).
- **Far too heavy** (load past ``OVERLOAD_MULTIPLIER × capacity``) AND
  physically exhausted → movement refuses, with an explicit message naming
  both the load and the exhaustion. Dropping something always works.

``ItemTemplate.weight`` — a dormant column since it was added — finally gets
its consumer. Worn gear is free (distributed weight, the convenience rule);
only loose inventory and a carried body count. All magnitudes PLACEHOLDER.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

# --- PLACEHOLDER magnitudes (#2862 author pass) ---
# Internal stat scale is 10-50 for the CG 1-5 range; capacity is deliberately
# GENEROUS — a middling character carries a full pack and a body for free.
CARRY_CAPACITY_BASE = 100
CARRY_CAPACITY_PER_STRENGTH = 5
# One unconscious (or dead) passenger, in weight units.
CARRIED_BODY_WEIGHT = 150
# Past this multiple of capacity the load is "far far too heavy".
OVERLOAD_MULTIPLIER = 2
# Physical fatigue charged per room moved while above capacity.
ENCUMBERED_MOVE_FATIGUE = 2
OVERLOADED_MOVE_FATIGUE = 6

OVERLOADED_EXHAUSTED_MSG = (
    "|rYou are carrying far too much, and you have nothing left to haul it "
    "with. Drop something, or rest.|n"
)
ENCUMBERED_MOVE_MSG = "|yThe load drags at you.|n"
OVERLOADED_MOVE_MSG = "|rYou stagger under far too much weight.|n"


class EncumbranceBand(Enum):
    FREE = "free"
    ENCUMBERED = "encumbered"
    OVERLOADED = "overloaded"


def carry_capacity(character: ObjectDB) -> int:
    """Generous strength-scaled capacity (weight units)."""
    strength = character.traits.get_trait_value("strength") or 0
    return CARRY_CAPACITY_BASE + strength * CARRY_CAPACITY_PER_STRENGTH


def carried_load(character: ObjectDB) -> int:
    """Total load: loose inventory weight + a carried body.

    Worn gear is free by rule — equipped instances are excluded, so dressing
    for war never encumbers; only what fills your arms and pack counts.
    """
    from world.items.models import EquippedItem  # noqa: PLC0415

    items = list(character.carried_items)
    if not items:
        load = 0
    else:
        equipped_ids = set(
            EquippedItem.objects.filter(item_instance__in=[item.pk for item in items]).values_list(
                "item_instance_id", flat=True
            )
        )
        load = sum(int(item.template.weight or 0) for item in items if item.pk not in equipped_ids)
    load += _carried_body_weight(character)
    return load


def encumbrance_band(character: ObjectDB) -> EncumbranceBand:
    """Which band the character's current load falls in."""
    capacity = carry_capacity(character)
    load = carried_load(character)
    if load <= capacity:
        return EncumbranceBand.FREE
    if load <= capacity * OVERLOAD_MULTIPLIER:
        return EncumbranceBand.ENCUMBERED
    return EncumbranceBand.OVERLOADED


def movement_blocked_message(character: ObjectDB) -> str | None:
    """The explicit refusal, or None when movement is allowed.

    Only the extreme combination blocks: OVERLOADED load AND a physically
    EXHAUSTED fatigue pool. Everything below that always moves (and pays).
    """
    if encumbrance_band(character) is not EncumbranceBand.OVERLOADED:
        return None
    from world.fatigue.constants import FatigueZone  # noqa: PLC0415
    from world.fatigue.services import get_fatigue_zone  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return None
    if get_fatigue_zone(sheet, "physical") == FatigueZone.EXHAUSTED:
        return OVERLOADED_EXHAUSTED_MSG
    return None


def charge_move_fatigue(character: ObjectDB) -> None:
    """Charge the per-room fatigue for an over-capacity move (post-arrival).

    FREE band: nothing, ever (the ruled invariant). The charge message is
    always shown when a cost lands — a player must never wonder where their
    fatigue went.
    """
    band = encumbrance_band(character)
    if band is EncumbranceBand.FREE:
        return
    from world.fatigue.constants import EffortLevel  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return
    if band is EncumbranceBand.ENCUMBERED:
        apply_fatigue(sheet, "physical", ENCUMBERED_MOVE_FATIGUE, EffortLevel.LOW)
        character.msg(ENCUMBERED_MOVE_MSG)
    else:
        apply_fatigue(sheet, "physical", OVERLOADED_MOVE_FATIGUE, EffortLevel.LOW)
        character.msg(OVERLOADED_MOVE_MSG)


def _carried_body_weight(character: ObjectDB) -> int:
    """The weight of a carried unconscious body, if any (#2852 carry)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.vitals.models import CarriedBody  # noqa: PLC0415

    try:
        sheet = character.character_sheet
    except (AttributeError, ObjectDoesNotExist):
        return 0
    if sheet is None:
        return 0
    if CarriedBody.objects.filter(carrier=sheet).exists():
        return CARRIED_BODY_WEIGHT
    return 0
