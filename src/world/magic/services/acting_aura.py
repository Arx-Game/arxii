"""The aura a character acts with: an active alternate self's affinity, else the true aura.

Power-side readers (the aura-alignment power term, resonance of place, covenant
affinity situations) read this. Identity-side readers (Fall threshold, Soul Tether,
atonement, the sheet display, gates) keep reading the true ``CharacterAura``.
Derive-on-read (ADR-0014): nothing is written when an alternate self is assumed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.magic.specialization.services import _active_alt_self_resonance
from world.magic.types.aura import ActingAura

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def acting_aura(sheet: CharacterSheet) -> ActingAura | None:
    """The aura ``sheet``'s character acts with right now.

    ``None`` when the sheet has no ``CharacterAura`` and no active alternate self
    carrying a resonance.
    """
    resonance = _active_alt_self_resonance(sheet)
    alternate_affinity = resonance.affinity if resonance is not None else None
    try:
        true_aura = sheet.aura
    except ObjectDoesNotExist:
        true_aura = None
    if true_aura is None and alternate_affinity is None:
        return None
    return ActingAura(true_aura=true_aura, alternate_affinity=alternate_affinity)
