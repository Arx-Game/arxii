"""Per-technique capability-requirement evaluation (agency gate)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import get_effective_capability_value

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models.techniques import Technique


def technique_performable(character: ObjectDB, technique: Technique) -> bool:
    """True if the character is not dead and meets every capability requirement
    of the technique (effective value >= minimum_value). Per-technique agency.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415 — vitals↔magic cycle

    if is_dead(character):
        return False
    for req in technique.capability_requirements.select_related("capability"):
        if get_effective_capability_value(character, req.capability) < req.minimum_value:
            return False
    return True
