"""How a modifier target is named and defined to a player (#4872, #5206).

A card prints its bonus as ``+10 sailing`` and shows the term's definition on hover; the
sheet's Bonuses band names and defines each target the same way. Both read these two
functions, so a term reads the same on a card and on the sheet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.mechanics.models import ModifierTarget


def term_label(target_name: str) -> str:
    """A modifier target's name as a card prints it: ``physical_development`` -> ``physical
    development``. Lowercase on purpose; the card's line reads ``+10 sailing``."""
    return target_name.replace("_", " ").strip().lower()


def term_definition(target: ModifierTarget) -> str:
    """A modifier target's definition, from the row that owns the term (ruled 2026-10-19).

    ``Trait.description`` for a target bound to a stat or skill, ``Aspect.description`` for
    one bound to an aspect, otherwise the target's own ``description``. A caller reading many
    targets selects ``target_trait`` and ``target_aspect`` so this runs no query.
    """
    if target.target_trait_id is not None:
        return target.target_trait.description
    if target.target_aspect_id is not None:
        return target.target_aspect.description
    return target.description
