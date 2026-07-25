"""Capability-requirement evaluation for casting (agency gate).

Two requirement sources feed one gate (#2700):

- **The technique** — what performing this ability demands of anyone
  (``TechniqueCapabilityRequirement``; a two-handed strike needs ``limb_use >= 2``).
- **The caster's style** — what working magic *this way* demands of the caster
  (``StyleCapabilityRequirement``, reached through ``Path.style``; an Incantation
  caster needs to be able to speak).

Both are evaluated against the same ``get_effective_capability_value`` oracle, so a
condition that zeroes a capability blocks either kind identically. Keeping them as one
gate rather than two is deliberate: the style set is caster-dependent, which the
per-technique set structurally cannot express, but the *question* they answer — "can
this character perform this cast right now" — is the same one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import get_effective_capability_value

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.techniques import Technique


def style_capability_requirements(character_sheet: CharacterSheet) -> list:
    """Capability requirements imposed by the caster's Path style (#2700).

    Empty when the character has no path (pre-awakening, NPCs) or their path
    authors no style — both are unrestricted, matching the pre-#2700 behaviour
    for a character outside the path system.
    """
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    path = current_path_for_character(character_sheet.character)
    if path is None or path.style_id is None:
        return []
    return path.style.cached_capability_requirements


def technique_performable(character_sheet: CharacterSheet | None, technique: Technique) -> bool:
    """True if the character is not dead and meets every capability requirement of
    both the technique and their own Path style (effective value >= minimum_value).

    A None character_sheet (NPC without sheet, etc.) is treated as not-performable.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    if character_sheet is None or is_dead(character_sheet):
        return False
    requirements = [
        *technique.capability_requirements.select_related("capability"),
        *style_capability_requirements(character_sheet),
    ]
    for req in requirements:
        if get_effective_capability_value(character_sheet, req.capability) < req.minimum_value:
            return False
    return True
